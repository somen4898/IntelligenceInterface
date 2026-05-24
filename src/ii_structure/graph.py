"""GraphStore — SQLite-backed code knowledge graph."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from typing import Any

from ii_structure.parser import SymbolInfo

logger = logging.getLogger(__name__)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_ENTRY_POINT_NAMES = {
    "main", "__main__", "__init__", "setup", "teardown",
    "setUp", "tearDown", "cli", "app", "run", "start",
    "configure", "register",
}

_ENTRY_POINT_PREFIXES = ("handle_", "on_", "test_")

_FRAMEWORK_DECORATORS = {
    "property", "abstractmethod", "staticmethod", "classmethod",
    "app.route", "app.get", "app.post", "app.put", "app.delete",
    "cli.command", "click.command", "click.group",
    "pytest.fixture", "fixture",
    "override", "overrides",
}


def _sanitize_name(s: str, max_len: int = 256) -> str:
    """Strip ASCII control chars (except tab/newline) and cap length."""
    s = _CONTROL_CHAR_RE.sub("", s)
    return s[:max_len]


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    signature TEXT,
    docstring TEXT,
    parent_name TEXT,
    decorators TEXT DEFAULT '[]',
    children TEXT DEFAULT '[]',
    file_hash TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_qualified TEXT NOT NULL,
    target_qualified TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_qualified ON nodes(qualified_name);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_qualified);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_qualified);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_edges_file ON edges(file_path);
"""


class GraphStore:
    """SQLite-backed code knowledge graph store."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-8000")
        self._conn.execute("PRAGMA mmap_size=268435456")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)

        # Run migrations (creates file_aux, FTS5, indexes)
        from ii_structure.migrations import get_schema_version, run_migrations
        if get_schema_version(self._conn) < 1:
            self._conn.execute(
                "INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '1')"
            )
            self._conn.commit()
        run_migrations(self._conn)

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.commit()
        self._conn.close()
        self._conn = None

    def __enter__(self) -> GraphStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ---- helpers ----

    @staticmethod
    def _make_qualified(name: str, file_path: str, parent: str | None) -> str:
        name = _sanitize_name(name)
        if parent:
            parent = _sanitize_name(parent)
            return f"{file_path}::{parent}.{name}"
        return f"{file_path}::{name}"

    # ---- write operations ----

    def upsert_node(
        self, symbol: SymbolInfo, file_path: str, file_hash: str
    ) -> int:
        qn = self._make_qualified(symbol.name, file_path, symbol.parent)
        now = time.time()
        cur = self._conn.execute(
            """\
            INSERT INTO nodes
                (kind, name, qualified_name, file_path, line_start, line_end,
                 signature, docstring, parent_name, decorators, children,
                 file_hash, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qualified_name) DO UPDATE SET
                kind=excluded.kind,
                name=excluded.name,
                file_path=excluded.file_path,
                line_start=excluded.line_start,
                line_end=excluded.line_end,
                signature=excluded.signature,
                docstring=excluded.docstring,
                parent_name=excluded.parent_name,
                decorators=excluded.decorators,
                children=excluded.children,
                file_hash=excluded.file_hash,
                updated_at=excluded.updated_at
            """,
            (
                symbol.kind,
                _sanitize_name(symbol.name),
                qn,
                file_path,
                symbol.line,
                symbol.end_line,
                symbol.signature,
                symbol.docstring,
                symbol.parent,
                json.dumps(symbol.decorators),
                json.dumps(symbol.children),
                file_hash,
                now,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def upsert_edge(
        self,
        kind: str,
        source_qualified: str,
        target_qualified: str,
        file_path: str,
        line: int = 0,
    ) -> int:
        now = time.time()
        cur = self._conn.execute(
            """\
            INSERT INTO edges (kind, source_qualified, target_qualified,
                               file_path, line, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, source_qualified, target_qualified, file_path, line)
            DO UPDATE SET updated_at=excluded.updated_at
            """,
            (kind, source_qualified, target_qualified, file_path, line, now),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def remove_file_data(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM file_aux WHERE file_path = ?", (file_path,))

    def store_file_nodes_edges(
        self,
        file_path: str,
        symbols: list[SymbolInfo],
        edges: list[Any],
        file_hash: str,
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self.remove_file_data(file_path)
            for sym in symbols:
                self.upsert_node(sym, file_path, file_hash)
            for edge in edges:
                if isinstance(edge, (list, tuple)):
                    self.upsert_edge(*edge)
                else:
                    # EdgeInfo-like object with attributes
                    src = getattr(edge, "source_qualified", None) or getattr(edge, "source", "")
                    tgt = getattr(edge, "target_qualified", None) or getattr(edge, "target", "")
                    self.upsert_edge(
                        edge.kind,
                        src,
                        tgt,
                        edge.file_path,
                        getattr(edge, "line", 0),
                    )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def commit(self) -> None:
        """Flush pending writes.

        With ``isolation_level=None`` (autocommit), individual operations
        commit automatically.  This method only has an effect after an
        explicit ``BEGIN`` transaction block.
        """
        self._conn.commit()

    def set_metadata(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value)
        )

    # --- file_aux CRUD ---

    def upsert_file_aux(
        self, file_path: str, imports_json: str, parse_error: str | None, content_hash: str
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO file_aux (file_path, imports_json, parse_error, content_hash) "
            "VALUES (?, ?, ?, ?)",
            (file_path, imports_json, parse_error, content_hash),
        )

    def get_file_aux(self, file_path: str) -> dict | None:
        row = self._conn.execute(
            "SELECT imports_json, parse_error, content_hash FROM file_aux WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return None
        return {
            "imports_json": row["imports_json"],
            "parse_error": row["parse_error"],
            "content_hash": row["content_hash"],
        }

    def remove_file_aux(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM file_aux WHERE file_path = ?", (file_path,))

    def get_all_file_aux_paths(self) -> list[str]:
        cur = self._conn.execute("SELECT file_path FROM file_aux ORDER BY file_path")
        return [r[0] for r in cur.fetchall()]

    # ---- read operations ----

    def get_node(self, qualified_name: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT * FROM nodes WHERE qualified_name = ?", (qualified_name,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def get_nodes_by_file(self, file_path: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM nodes WHERE file_path = ?", (file_path,)
        )
        return [dict(r) for r in cur.fetchall()]

    def get_edges_by_target(
        self, qualified_name: str
    ) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM edges WHERE target_qualified = ?", (qualified_name,)
        )
        return [dict(r) for r in cur.fetchall()]

    def get_all_files(self) -> list[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT file_path FROM nodes ORDER BY file_path"
        )
        return [r[0] for r in cur.fetchall()]

    def get_stats(self) -> dict[str, int]:
        nodes = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {"total_nodes": nodes, "total_edges": edges}

    # ---- analysis queries ----

    def get_impact_radius(
        self,
        qualified_name: str,
        max_depth: int = 3,
        max_nodes: int = 200,
    ) -> dict[str, Any]:
        """Blast radius via recursive CTE."""
        seed = self.get_node(qualified_name)
        if seed is None:
            return {
                "changed_node": None,
                "impacted_nodes": [],
                "impacted_files": [],
                "total_impacted": 0,
            }

        self._conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _impact_seeds (qn TEXT)"
        )
        self._conn.execute("DELETE FROM _impact_seeds")
        self._conn.execute(
            "INSERT INTO _impact_seeds (qn) VALUES (?)", (qualified_name,)
        )

        rows = self._conn.execute(
            """\
            WITH RECURSIVE impacted(node_qn, depth) AS (
                SELECT qn, 0 FROM _impact_seeds
                UNION
                SELECT e.source_qualified, i.depth + 1
                FROM impacted i JOIN edges e ON e.target_qualified = i.node_qn
                WHERE i.depth < ?
                UNION
                SELECT e.target_qualified, i.depth + 1
                FROM impacted i JOIN edges e ON e.source_qualified = i.node_qn
                WHERE i.depth < ?
            )
            SELECT DISTINCT node_qn, MIN(depth) AS min_depth
            FROM impacted GROUP BY node_qn LIMIT ?
            """,
            (max_depth, max_depth, max_nodes),
        ).fetchall()

        impacted_nodes: list[dict[str, Any]] = []
        impacted_files: set[str] = set()
        for row in rows:
            qn = row["node_qn"]
            depth = row["min_depth"]
            if qn == qualified_name:
                continue
            node = self.get_node(qn)
            if node is not None:
                node["depth"] = depth
                impacted_nodes.append(node)
                impacted_files.add(node["file_path"])

        self._conn.execute("DROP TABLE IF EXISTS _impact_seeds")

        return {
            "changed_node": seed,
            "impacted_nodes": impacted_nodes,
            "impacted_files": sorted(impacted_files),
            "total_impacted": len(impacted_nodes),
        }

    def get_dead_symbols(
        self, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Find function/method nodes with zero incoming CALLS edges."""
        where = "WHERE n.kind IN ('function', 'method')"
        params: list[str] = []
        if file_path:
            where += " AND n.file_path = ?"
            params.append(file_path)

        sql = f"""
        SELECT n.* FROM nodes n
        {where}
        AND n.qualified_name NOT IN (
            SELECT target_qualified FROM edges WHERE kind = 'CALLS'
        )
        ORDER BY n.file_path, n.line_start
        """
        cur = self._conn.execute(sql, params)
        results: list[dict[str, Any]] = []
        for row in cur.fetchall():
            d = dict(row)
            name = d["name"]
            fp = d["file_path"]

            # Exclude entry point names
            if name in _ENTRY_POINT_NAMES:
                continue

            # Exclude entry point prefixes (test_, handle_, on_)
            if any(name.startswith(p) for p in _ENTRY_POINT_PREFIXES):
                continue

            # Exclude test files
            base = fp.rsplit("/", 1)[-1] if "/" in fp else fp
            if base.startswith("test_") or "/test_" in fp or fp.startswith("tests/"):
                continue

            # Exclude dunder methods (invoked by runtime)
            if name.startswith("__") and name.endswith("__"):
                continue

            # Exclude constructors (JS/TS)
            if name == "constructor":
                continue

            # Exclude conftest.py (pytest fixtures)
            if fp.endswith("conftest.py"):
                continue

            # Exclude functions with framework decorators
            decorators = json.loads(d.get("decorators") or "[]")
            if decorators and any(
                any(fd in dec for fd in _FRAMEWORK_DECORATORS)
                for dec in decorators
            ):
                continue

            results.append(d)
        return results

    def get_transitive_tests(
        self, qualified_name: str, max_depth: int = 2
    ) -> list[dict[str, Any]]:
        """Find test coverage (direct and transitive)."""
        tests: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Direct: TESTED_BY edges targeting this node
        direct_edges = self._conn.execute(
            "SELECT source_qualified FROM edges WHERE kind = 'TESTED_BY' AND target_qualified = ?",
            (qualified_name,),
        ).fetchall()
        for row in direct_edges:
            src_qn = row["source_qualified"]
            if src_qn in seen:
                continue
            seen.add(src_qn)
            node = self.get_node(src_qn)
            if node is not None:
                node["indirect"] = False
                tests.append(node)

        # Transitive: BFS callers up to max_depth, then collect TESTED_BY
        frontier = {qualified_name}
        for _depth in range(max_depth):
            next_frontier: set[str] = set()
            for qn in frontier:
                callers = self._conn.execute(
                    "SELECT source_qualified FROM edges WHERE kind = 'CALLS' AND target_qualified = ?",
                    (qn,),
                ).fetchall()
                for crow in callers:
                    caller_qn = crow["source_qualified"]
                    if caller_qn in seen:
                        continue
                    next_frontier.add(caller_qn)
                    # Check if this caller has TESTED_BY edges
                    tested_edges = self._conn.execute(
                        "SELECT source_qualified FROM edges WHERE kind = 'TESTED_BY' AND target_qualified = ?",
                        (caller_qn,),
                    ).fetchall()
                    for trow in tested_edges:
                        test_qn = trow["source_qualified"]
                        if test_qn in seen:
                            continue
                        seen.add(test_qn)
                        node = self.get_node(test_qn)
                        if node is not None:
                            node["indirect"] = True
                            tests.append(node)
            frontier = next_frontier

        return tests

    def batch_get_nodes(self, qualified_names: set[str]) -> list[dict]:
        """Fetch multiple nodes in one query instead of N get_node calls."""
        if not qualified_names:
            return []
        qn_list = list(qualified_names)
        batch_size = 450
        results = []
        for i in range(0, len(qn_list), batch_size):
            batch = qn_list[i:i + batch_size]
            placeholders = ",".join("?" for _ in batch)
            rows = self._conn.execute(
                f"SELECT * FROM nodes WHERE qualified_name IN ({placeholders})",  # noqa: S608
                batch,
            ).fetchall()
            results.extend(dict(r) for r in rows)
        return results

    def rebuild_fts_index(self) -> int:
        """Rebuild the FTS5 index from the nodes table."""
        self._conn.execute("DROP TABLE IF EXISTS nodes_fts")
        self._conn.execute("""
            CREATE VIRTUAL TABLE nodes_fts USING fts5(
                name, qualified_name, file_path,
                content='nodes', content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        self._conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")
        self._conn.commit()
        count = self._conn.execute("SELECT count(*) FROM nodes_fts").fetchone()[0]
        logger.info("FTS index rebuilt: %d rows", count)
        return count

    def search_fts(self, query: str, limit: int = 20) -> list[dict]:
        """Search nodes using FTS5. Falls back to LIKE if FTS5 unavailable."""
        words = query.split()
        if not words:
            return []

        # FTS5 search
        try:
            fts_query = " AND ".join(
                '"' + w.replace('"', '""') + '"' for w in words
            )
            rows = self._conn.execute(
                "SELECT n.* FROM nodes_fts f "
                "JOIN nodes n ON f.rowid = n.id "
                "WHERE nodes_fts MATCH ? LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except Exception:
            pass

        # LIKE fallback
        conditions = []
        params: list[str | int] = []
        for word in words:
            conditions.append("(LOWER(name) LIKE ? OR LOWER(qualified_name) LIKE ?)")
            params.extend([f"%{word.lower()}%", f"%{word.lower()}%"])
        where = " AND ".join(conditions)
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM nodes WHERE {where} LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_bare_call_targets(self) -> int:
        """Post-processing pass to resolve bare call targets."""
        # Find bare CALLS edges
        bare_edges = self._conn.execute(
            "SELECT id, source_qualified, target_qualified, file_path "
            "FROM edges WHERE kind = 'CALLS' AND target_qualified NOT LIKE '%::%'"
        ).fetchall()

        if not bare_edges:
            return 0

        # Build name → [qualified_names] lookup
        all_nodes = self._conn.execute(
            "SELECT name, qualified_name, file_path FROM nodes"
        ).fetchall()
        name_to_qns: dict[str, list[tuple[str, str]]] = {}
        for row in all_nodes:
            name_to_qns.setdefault(row["name"], []).append(
                (row["qualified_name"], row["file_path"])
            )

        # Build import map: source_file → set[imported_files]
        import_edges = self._conn.execute(
            "SELECT source_qualified, target_qualified, file_path FROM edges WHERE kind = 'IMPORTS'"
        ).fetchall()
        file_imports: dict[str, set[str]] = {}
        for row in import_edges:
            src_file = row["file_path"]
            tgt_qn = row["target_qualified"]
            if "::" in tgt_qn:
                tgt_file = tgt_qn.split("::")[0]
                file_imports.setdefault(src_file, set()).add(tgt_file)

        resolved = 0
        for edge in bare_edges:
            bare_name = edge["target_qualified"]

            # Handle import-qualified targets like "services.create_user"
            module_hint = None
            lookup_name = bare_name
            if "." in bare_name:
                parts = bare_name.rsplit(".", 1)
                module_hint = parts[0]
                lookup_name = parts[1]

            candidates = name_to_qns.get(lookup_name, [])
            if not candidates:
                continue

            # If we have a module hint, prefer candidates from matching files
            if module_hint and len(candidates) > 1:
                hint_matching = [
                    (qn, fp) for qn, fp in candidates
                    if module_hint in fp
                ]
                if hint_matching:
                    candidates = hint_matching

            if len(candidates) == 1:
                self._conn.execute(
                    "UPDATE edges SET target_qualified = ? WHERE id = ?",
                    (candidates[0][0], edge["id"]),
                )
                resolved += 1
            else:
                # Try to disambiguate via imports
                caller_file = edge["file_path"]
                imported_files = file_imports.get(caller_file, set())
                matching = [
                    (qn, fp) for qn, fp in candidates if fp in imported_files
                ]
                if len(matching) == 1:
                    self._conn.execute(
                        "UPDATE edges SET target_qualified = ? WHERE id = ?",
                        (matching[0][0], edge["id"]),
                    )
                    resolved += 1

        return resolved
