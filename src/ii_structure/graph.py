"""GraphStore — SQLite-backed code knowledge graph."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any

from ii_structure.parser import SymbolInfo

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


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
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        # Set schema version if not already set
        self._conn.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '1')"
        )

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
        existing = self._conn.execute(
            "SELECT id FROM edges WHERE kind=? AND source_qualified=? AND target_qualified=? AND file_path=? AND line=?",
            (kind, source_qualified, target_qualified, file_path, line),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE edges SET updated_at=? WHERE id=?",
                (now, existing["id"]),
            )
            return existing["id"]
        cur = self._conn.execute(
            """\
            INSERT INTO edges (kind, source_qualified, target_qualified,
                               file_path, line, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kind, source_qualified, target_qualified, file_path, line, now),
        )
        return cur.lastrowid  # type: ignore[return-value]

    def remove_file_data(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))

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
                    self.upsert_edge(
                        edge.kind,
                        edge.source_qualified,
                        edge.target_qualified,
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

    def get_edges_by_source(
        self, qualified_name: str
    ) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM edges WHERE source_qualified = ?", (qualified_name,)
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
