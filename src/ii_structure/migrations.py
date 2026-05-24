"""Schema migration framework for ii-structure SQLite database.

Each migration is idempotent (uses IF NOT EXISTS / column checks).
Migrations run in individual transactions with version bumped after each.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Callable

logger = logging.getLogger(__name__)

_KNOWN_TABLES = frozenset({
    "nodes", "edges", "metadata", "file_aux", "nodes_fts",
})


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from the metadata table."""
    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return 1
        return int(row[0] if isinstance(row, (tuple, list)) else row["value"])
    except sqlite3.OperationalError:
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    if table not in _KNOWN_TABLES:
        raise ValueError(f"Unknown table: {table}")
    row = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row[0] > 0


# --- Migration functions ---

def _migrate_v2(conn: sqlite3.Connection) -> None:
    """v2: Create file_aux table (moved from _ensure_aux_table)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_aux (
            file_path TEXT PRIMARY KEY,
            imports_json TEXT NOT NULL DEFAULT '[]',
            parse_error TEXT,
            content_hash TEXT
        )
    """)
    logger.info("Migration v2: created file_aux table")


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """v3: Add composite edge index for upsert_edge performance."""
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_edges_composite
        ON edges(kind, source_qualified, target_qualified, file_path, line)
    """)
    logger.info("Migration v3: created composite edge index")


def _migrate_v4(conn: sqlite3.Connection) -> None:
    """v4: Create FTS5 virtual table for node search."""
    if not _table_exists(conn, "nodes_fts"):
        conn.execute("""
            CREATE VIRTUAL TABLE nodes_fts USING fts5(
                name, qualified_name, file_path,
                content='nodes', content_rowid='id',
                tokenize='porter unicode61'
            )
        """)
        logger.info("Migration v4: created nodes_fts FTS5 table")


def _migrate_v5(conn: sqlite3.Connection) -> None:
    """v5: Add name index on nodes (for exact lookups)."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name)"
    )
    logger.info("Migration v5: added idx_nodes_name index")


# --- Migration registry ---

MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_v2,
    3: _migrate_v3,
    4: _migrate_v4,
    5: _migrate_v5,
}

LATEST_VERSION = max(MIGRATIONS.keys())


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all pending migrations in order."""
    current = get_schema_version(conn)
    if current >= LATEST_VERSION:
        return

    logger.info("Schema version %d -> %d: running migrations", current, LATEST_VERSION)

    for version in sorted(MIGRATIONS.keys()):
        if version <= current:
            continue
        logger.info("Running migration v%d", version)
        try:
            MIGRATIONS[version](conn)
            _set_schema_version(conn, version)
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            logger.error("Migration v%d failed", version, exc_info=True)
            raise

    logger.info("Migrations complete, now at schema version %d", LATEST_VERSION)
