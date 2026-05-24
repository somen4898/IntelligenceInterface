"""Tests for ii_structure.migrations — versioned schema migration framework."""
import sqlite3
import pytest
from ii_structure.migrations import (
    get_schema_version,
    run_migrations,
    LATEST_VERSION,
)


@pytest.fixture
def fresh_db(tmp_path):
    """Return a connection to a fresh SQLite DB with base schema."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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
        INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '1');
    """)
    conn.commit()
    yield conn
    conn.close()


def test_get_schema_version_fresh(fresh_db):
    assert get_schema_version(fresh_db) == 1


def test_get_schema_version_no_metadata():
    conn = sqlite3.connect(":memory:")
    assert get_schema_version(conn) == 0
    conn.close()


def test_run_migrations_from_v1(fresh_db):
    run_migrations(fresh_db)
    assert get_schema_version(fresh_db) == LATEST_VERSION


def test_migrations_are_idempotent(fresh_db):
    run_migrations(fresh_db)
    v1 = get_schema_version(fresh_db)
    run_migrations(fresh_db)
    v2 = get_schema_version(fresh_db)
    assert v1 == v2 == LATEST_VERSION


def test_migration_v2_adds_file_aux(fresh_db):
    run_migrations(fresh_db)
    row = fresh_db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='file_aux'"
    ).fetchone()
    assert row[0] == 1


def test_migration_v3_adds_composite_edge_index(fresh_db):
    run_migrations(fresh_db)
    indexes = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_edges_composite'"
    ).fetchone()
    assert indexes is not None


def test_migration_v4_adds_fts(fresh_db):
    run_migrations(fresh_db)
    row = fresh_db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
    ).fetchone()
    assert row[0] == 1


def test_migration_v5_adds_nodes_name_index(fresh_db):
    run_migrations(fresh_db)
    indexes = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_nodes_name'"
    ).fetchone()
    assert indexes is not None
