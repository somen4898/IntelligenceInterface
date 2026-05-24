import hashlib
import json
import logging
import pathlib
import sqlite3
from dataclasses import asdict

import pathspec

from ii_structure.backends import get_backend, supported_extensions
from ii_structure.graph import GraphStore

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules", ".ii-structure", ".pytest_cache"}


# ---------------------------------------------------------------------------
# _FilesView — dict-like facade over GraphStore for backward compatibility
# ---------------------------------------------------------------------------

class _FilesView:
    """Dict-like view over GraphStore so ``idx.files[path]`` keeps working."""

    def __init__(self, graph: GraphStore):
        self._graph = graph

    def __contains__(self, key):
        if self._graph.get_nodes_by_file(key):
            return True
        return self._graph.get_file_aux(key) is not None

    def __getitem__(self, key):
        nodes = self._graph.get_nodes_by_file(key)
        aux = self._graph.get_file_aux(key)

        if not nodes and aux is None:
            raise KeyError(key)

        symbols = [_node_to_symbol(n) for n in nodes]
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
        """Write commands call ``idx.files[path] = _parse_and_build_entry(f)``."""
        from ii_structure.parser import SymbolInfo

        fhash = value.get("content_hash", "")
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
        imports_json = json.dumps(value.get("imports", []))
        parse_error = value.get("parse_error")
        self._graph.upsert_file_aux(key, imports_json, parse_error, fhash)

    def __delitem__(self, key):
        self._graph.remove_file_data(key)

    def __len__(self):
        node_files = set(self._graph.get_all_files())
        aux_files = set(self._graph.get_all_file_aux_paths())
        return len(node_files | aux_files)

    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        node_files = set(self._graph.get_all_files())
        aux_files = set(self._graph.get_all_file_aux_paths())
        return sorted(node_files | aux_files)

    def items(self):
        for f in self.keys():
            yield f, self[f]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def _node_to_symbol(node: dict) -> dict:
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
# _process_file — parse a single file and store results in the graph
# ---------------------------------------------------------------------------

def _process_file(
    rel: str,
    content: str,
    source_file: pathlib.Path,
    graph: GraphStore,
) -> None:
    """Parse a single file and store results in the graph."""
    backend = get_backend(str(source_file))
    result = backend.parse_file(rel, content)
    fhash = _content_hash(content)
    graph.store_file_nodes_edges(rel, result.symbols, result.edges, fhash)
    imports_json = json.dumps([asdict(i) for i in result.imports])
    graph.upsert_file_aux(rel, imports_json, result.error, fhash)


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

        gitignore_spec = _load_gitignore(root)
        for source_file in _walk_source_files(root, gitignore_spec):
            rel = str(source_file.relative_to(root))
            try:
                content = source_file.read_text(encoding="utf-8", errors="replace")
            except (FileNotFoundError, PermissionError) as exc:
                logger.warning("Skipping %s: %s", rel, exc)
                continue
            _process_file(rel, content, source_file, graph)

        graph.resolve_bare_call_targets()
        graph.rebuild_fts_index()
        graph.set_metadata("project_root", str(root))
        graph.commit()
        return cls(project_root=str(root), graph=graph)

    @classmethod
    def load(cls, state_dir: pathlib.Path) -> "Index":
        db_path = state_dir / "graph.db"
        if not db_path.exists():
            raise FileNotFoundError(f"No graph.db in {state_dir}")
        graph = GraphStore(str(db_path))
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
        existing_files.update(self.graph.get_all_file_aux_paths())

        for source_file in _walk_source_files(root, gitignore_spec):
            rel = str(source_file.relative_to(root))
            current_files.add(rel)

            try:
                content = source_file.read_text(encoding="utf-8", errors="replace")
            except (FileNotFoundError, PermissionError) as exc:
                logger.warning("Skipping %s: %s", rel, exc)
                continue

            actual_hash = _content_hash(content)
            aux = self.graph.get_file_aux(rel)
            if aux and aux["content_hash"] == actual_hash:
                continue

            _process_file(rel, content, source_file, graph=self.graph)

        for old_file in existing_files - current_files:
            self.graph.remove_file_data(old_file)

        self.graph.resolve_bare_call_targets()
        self.graph.rebuild_fts_index()
        self.graph.commit()
        self._invalidate_cache()

    # -- queries (public API) -----------------------------------------------

    def search_symbols(self, name_path: str) -> list[dict]:
        """Search by name path — FTS5 first, then exact match fallback."""
        parts = name_path.strip("/").split("/")

        # Fast path: single name — use indexed SQL lookup
        if len(parts) == 1:
            name = parts[0]
            rows = self.graph._conn.execute(
                "SELECT * FROM nodes WHERE name = ?", (name,)
            ).fetchall()
            if rows:
                results = []
                for node in rows:
                    sym = _node_to_symbol(dict(node))
                    sym["file"] = node["file_path"]
                    results.append(sym)
                return results

        # Multi-part path: Parent/child lookup
        if len(parts) == 2:
            results = []
            for rel_path in self.graph.get_all_files():
                for node in self.graph.get_nodes_by_file(rel_path):
                    sym = _node_to_symbol(node)
                    sym["file"] = rel_path
                    parent = sym.get("parent") or ""
                    parent_match = (
                        parent == parts[0]
                        or parent.endswith("/" + parts[0])
                    )
                    if sym["name"] == parts[-1] and parent_match:
                        results.append(sym)
            return results

        # N-part path: full path match
        results = []
        for rel_path in self.graph.get_all_files():
            for node in self.graph.get_nodes_by_file(rel_path):
                sym = _node_to_symbol(node)
                sym["file"] = rel_path
                full_path = sym["name"]
                if sym.get("parent"):
                    full_path = f"{sym['parent']}/{sym['name']}"
                if full_path == name_path.strip("/"):
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
        except (FileNotFoundError, sqlite3.OperationalError) as exc:
            logger.warning("Failed to load index, rebuilding: %s", exc)

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
