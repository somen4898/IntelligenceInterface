import hashlib
import json
import pathlib
from dataclasses import asdict

import pathspec

from ii_structure.backends import get_backend, supported_extensions
from ii_structure.graph import GraphStore

INDEX_VERSION = 1
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules", ".ii-structure", ".pytest_cache"}

# ---------------------------------------------------------------------------
# Auxiliary table for per-file metadata not covered by the nodes/edges schema
# (imports JSON, parse_error).  Created alongside the graph tables.
# ---------------------------------------------------------------------------
_AUX_SCHEMA = """\
CREATE TABLE IF NOT EXISTS file_aux (
    file_path TEXT PRIMARY KEY,
    imports_json TEXT NOT NULL DEFAULT '[]',
    parse_error TEXT,
    content_hash TEXT
);
"""


def _ensure_aux_table(conn):
    """Create the file_aux table if it does not exist."""
    conn.executescript(_AUX_SCHEMA)


# ---------------------------------------------------------------------------
# _FilesView — dict-like facade over GraphStore for backward compatibility
# ---------------------------------------------------------------------------

class _FilesView:
    """Dict-like view over GraphStore so ``idx.files[path]`` keeps working."""

    def __init__(self, graph: GraphStore):
        self._graph = graph
        self._conn = graph._conn
        _ensure_aux_table(self._conn)

    # -- dict protocol -----------------------------------------------------

    def __contains__(self, key):
        # A file is "in" the index if it has nodes OR an aux row
        if self._graph.get_nodes_by_file(key):
            return True
        row = self._conn.execute(
            "SELECT 1 FROM file_aux WHERE file_path = ?", (key,)
        ).fetchone()
        return row is not None

    def __getitem__(self, key):
        nodes = self._graph.get_nodes_by_file(key)
        aux = self._conn.execute(
            "SELECT imports_json, parse_error, content_hash FROM file_aux WHERE file_path = ?",
            (key,),
        ).fetchone()

        if not nodes and aux is None:
            raise KeyError(key)

        symbols = [_node_to_old_symbol(n) for n in nodes]
        imports_json = aux["imports_json"] if aux else "[]"
        parse_error = aux["parse_error"] if aux else None
        content_hash = aux["content_hash"] if aux else ""

        return {
            "symbols": symbols,
            "imports": json.loads(imports_json),
            "mtime": 0,
            "content_hash": content_hash,
            "parse_error": parse_error,
        }

    def __setitem__(self, key, value):
        """Write commands call ``idx.files[path] = _parse_and_build_entry(f)``.

        *value* is the old-format dict with ``symbols``, ``imports``,
        ``content_hash``, ``parse_error``.  We convert back to
        ``SymbolInfo`` objects and push into the graph.
        """
        from ii_structure.parser import SymbolInfo

        fhash = value.get("content_hash", "")

        # Convert symbol dicts → SymbolInfo
        sym_objects = []
        for s in value.get("symbols", []):
            sym_objects.append(SymbolInfo(
                name=s["name"],
                kind=s["kind"],
                line=s["line"],
                end_line=s["end_line"],
                signature=s["signature"],
                docstring=s.get("docstring"),
                parent=s.get("parent"),
                children=s.get("children", []),
                decorators=s.get("decorators", []),
            ))

        self._graph.store_file_nodes_edges(key, sym_objects, [], fhash)

        # Store aux data
        imports_json = json.dumps(value.get("imports", []))
        parse_error = value.get("parse_error")
        self._conn.execute(
            "INSERT OR REPLACE INTO file_aux (file_path, imports_json, parse_error, content_hash) "
            "VALUES (?, ?, ?, ?)",
            (key, imports_json, parse_error, fhash),
        )

    def __delitem__(self, key):
        self._graph.remove_file_data(key)
        self._conn.execute("DELETE FROM file_aux WHERE file_path = ?", (key,))

    def __len__(self):
        # Count distinct files across nodes + aux
        row = self._conn.execute(
            "SELECT COUNT(*) FROM ("
            "  SELECT file_path FROM nodes "
            "  UNION "
            "  SELECT file_path FROM file_aux"
            ")"
        ).fetchone()
        return row[0]

    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        cur = self._conn.execute(
            "SELECT file_path FROM ("
            "  SELECT DISTINCT file_path FROM nodes "
            "  UNION "
            "  SELECT file_path FROM file_aux"
            ") ORDER BY file_path"
        )
        return [r[0] for r in cur.fetchall()]

    def items(self):
        for f in self.keys():
            yield f, self[f]

    def values(self):
        for f in self.keys():
            yield self[f]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def _node_to_old_symbol(node: dict) -> dict:
    """Convert a GraphStore node row to the old symbol dict format."""
    return {
        "name": node["name"],
        "kind": node["kind"],
        "line": node["line_start"],
        "end_line": node["line_end"],
        "signature": node.get("signature", ""),
        "docstring": node.get("docstring"),
        "parent": node.get("parent_name"),
        "children": json.loads(node.get("children") or "[]"),
        "decorators": json.loads(node.get("decorators") or "[]"),
    }


# ---------------------------------------------------------------------------
# Index class — wraps GraphStore
# ---------------------------------------------------------------------------

class Index:
    """In-memory index of all source symbols, imports, and metadata for a project.

    Backed by SQLite via ``GraphStore``.  The public API is unchanged so
    existing commands continue to work.
    """

    def __init__(self, project_root: str, graph: GraphStore):
        self.project_root = project_root
        self.graph = graph
        self.version = INDEX_VERSION
        self._files_cache: _FilesView | None = None

    @property
    def files(self) -> _FilesView:
        """Backward-compatible dict-like view over the graph."""
        if self._files_cache is None:
            self._files_cache = _FilesView(self.graph)
        return self._files_cache

    def _invalidate_cache(self):
        self._files_cache = None

    # -- construction -------------------------------------------------------

    @classmethod
    def build(cls, root: pathlib.Path) -> "Index":
        root = root.resolve()
        state_dir = root / ".ii-structure"
        state_dir.mkdir(parents=True, exist_ok=True)
        db_path = state_dir / "graph.db"
        graph = GraphStore(str(db_path))
        _ensure_aux_table(graph._conn)

        gitignore_spec = _load_gitignore(root)
        for source_file in _walk_source_files(root, gitignore_spec):
            rel = str(source_file.relative_to(root))
            content = source_file.read_text(encoding="utf-8", errors="replace")
            backend = get_backend(str(source_file))
            result = backend.parse_file(str(source_file), content)
            fhash = _content_hash(content)

            # Store nodes + edges
            graph.store_file_nodes_edges(rel, result.symbols, result.edges, fhash)

            # Store aux data (imports, parse_error)
            imports_json = json.dumps([asdict(i) for i in result.imports])
            graph._conn.execute(
                "INSERT OR REPLACE INTO file_aux (file_path, imports_json, parse_error, content_hash) "
                "VALUES (?, ?, ?, ?)",
                (rel, imports_json, result.error, fhash),
            )

        graph.resolve_bare_call_targets()
        # Store project_root in metadata
        graph._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('project_root', ?)",
            (str(root),),
        )
        graph.commit()
        return cls(project_root=str(root), graph=graph)

    @classmethod
    def load(cls, state_dir: pathlib.Path) -> "Index":
        db_path = state_dir / "graph.db"
        if not db_path.exists():
            raise FileNotFoundError(f"No graph.db in {state_dir}")
        graph = GraphStore(str(db_path))
        _ensure_aux_table(graph._conn)
        # Read project_root from metadata, fall back to deriving from state_dir
        row = graph._conn.execute(
            "SELECT value FROM metadata WHERE key = 'project_root'"
        ).fetchone()
        root = row[0] if row else str(state_dir.parent)
        return cls(project_root=root, graph=graph)

    # -- persistence --------------------------------------------------------

    def save(self, state_dir: pathlib.Path) -> None:
        import sqlite3

        state_dir.mkdir(parents=True, exist_ok=True)
        self.graph.commit()

        # If the graph DB isn't in state_dir yet, back it up there so that
        # ``load(state_dir)`` works later.
        current_db = pathlib.Path(self.graph._conn.execute(
            "PRAGMA database_list"
        ).fetchone()[2])
        target_db = state_dir / "graph.db"
        if current_db.resolve() != target_db.resolve():
            dst = sqlite3.connect(str(target_db))
            self.graph._conn.backup(dst)
            dst.close()

    # -- refresh ------------------------------------------------------------

    def refresh(self, root: pathlib.Path) -> None:
        root = root.resolve()
        gitignore_spec = _load_gitignore(root)
        current_files: set[str] = set()
        existing_files = set(self.graph.get_all_files())

        # Also include files that only have aux rows (e.g. parse-error-only files)
        aux_files = self.graph._conn.execute(
            "SELECT file_path FROM file_aux"
        ).fetchall()
        for row in aux_files:
            existing_files.add(row[0])

        for source_file in _walk_source_files(root, gitignore_spec):
            rel = str(source_file.relative_to(root))
            current_files.add(rel)

            content = source_file.read_text(encoding="utf-8", errors="replace")
            actual_hash = _content_hash(content)

            # Check if file changed via content hash
            aux = self.graph._conn.execute(
                "SELECT content_hash FROM file_aux WHERE file_path = ?", (rel,)
            ).fetchone()
            if aux and aux[0] == actual_hash:
                continue  # unchanged

            # Re-parse
            backend = get_backend(str(source_file))
            result = backend.parse_file(str(source_file), content)
            self.graph.store_file_nodes_edges(rel, result.symbols, result.edges, actual_hash)

            imports_json = json.dumps([asdict(i) for i in result.imports])
            self.graph._conn.execute(
                "INSERT OR REPLACE INTO file_aux (file_path, imports_json, parse_error, content_hash) "
                "VALUES (?, ?, ?, ?)",
                (rel, imports_json, result.error, actual_hash),
            )

        # Remove deleted files
        for old_file in existing_files - current_files:
            self.graph.remove_file_data(old_file)
            self.graph._conn.execute(
                "DELETE FROM file_aux WHERE file_path = ?", (old_file,)
            )

        self.graph.resolve_bare_call_targets()
        self.graph.commit()
        self._invalidate_cache()

    # -- queries (public API) -----------------------------------------------

    def get_symbols(self, rel_path: str) -> list[dict]:
        nodes = self.graph.get_nodes_by_file(rel_path)
        return [_node_to_old_symbol(n) for n in nodes]

    def search_symbols(self, name_path: str) -> list[dict]:
        """Search by name path — same matching logic as before."""
        results = []
        parts = name_path.strip("/").split("/")

        for rel_path in self.graph.get_all_files():
            for node in self.graph.get_nodes_by_file(rel_path):
                sym = _node_to_old_symbol(node)
                sym["file"] = rel_path

                if len(parts) == 1:
                    if sym["name"] == parts[0]:
                        results.append(sym)
                elif len(parts) == 2:
                    parent = sym.get("parent") or ""
                    parent_match = (
                        parent == parts[0]
                        or parent.endswith("/" + parts[0])
                    )
                    if sym["name"] == parts[-1] and parent_match:
                        results.append(sym)
                else:
                    full_path = sym["name"]
                    if sym.get("parent"):
                        full_path = f"{sym['parent']}/{sym['name']}"
                    if full_path == name_path.strip("/"):
                        results.append(sym)

        return results

    def all_symbols(self) -> list[dict]:
        results = []
        for rel_path in self.graph.get_all_files():
            for node in self.graph.get_nodes_by_file(rel_path):
                sym = _node_to_old_symbol(node)
                sym["file"] = rel_path
                results.append(sym)
        return results


# ---------------------------------------------------------------------------
# Module-level helpers (public — used by other modules)
# ---------------------------------------------------------------------------

def load_or_build_index(root: pathlib.Path) -> Index:
    state_dir = root / ".ii-structure"
    db_path = state_dir / "graph.db"

    # Auto-migration: if old JSON exists but no graph.db, rebuild
    json_path = state_dir / "index.json"
    if json_path.exists() and not db_path.exists():
        idx = Index.build(root)
        json_path.unlink()
        return idx

    if db_path.exists():
        try:
            idx = Index.load(state_dir)
            idx.refresh(root)
            idx.save(state_dir)
            return idx
        except Exception:
            pass

    idx = Index.build(root)
    idx.save(state_dir)
    return idx


def _content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _load_gitignore(root: pathlib.Path) -> pathspec.PathSpec | None:
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        patterns = gitignore_path.read_text().splitlines()
        return pathspec.PathSpec.from_lines("gitignore", patterns)
    return None


def _walk_source_files(
    root: pathlib.Path,
    gitignore_spec: pathspec.PathSpec | None,
) -> list[pathlib.Path]:
    files = []
    extensions = supported_extensions()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if gitignore_spec and gitignore_spec.match_file(str(rel)):
            continue
        files.append(path)
    return files
