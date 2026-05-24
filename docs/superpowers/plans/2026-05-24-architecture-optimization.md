# ii-structure Architecture & Performance Optimization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce token usage and improve performance by fixing architectural leaks, adding proper indexing/search, parallel parsing, schema migrations, and eliminating dead code.

**Architecture:** Encapsulate all SQL in GraphStore, add FTS5 search, parallel file parsing, a migration framework, and split the monolithic CLI. Inspired by patterns from code-review-graph.

**Tech Stack:** Python 3.10+, SQLite (WAL, FTS5, recursive CTEs), concurrent.futures, tree-sitter, click

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ii_structure/graph.py` | Modify | Add file_aux CRUD, composite index, FTS5, batch node fetch, upsert_edge ON CONFLICT, SQLite PRAGMAs, logging |
| `src/ii_structure/migrations.py` | Create | Schema migration framework (versioned, idempotent) |
| `src/ii_structure/index.py` | Modify | Use GraphStore file_aux methods, extract `_process_file`, parallel parsing, git ls-files, remove dead methods, logging |
| `src/ii_structure/resolver.py` | Modify | Remove try/except on jedi import |
| `src/ii_structure/cli.py` | Modify | Remove init/benchmark commands, keep command dispatch |
| `src/ii_structure/commands/init_cmd.py` | Create | CLAUDE_MD_SECTION + init command |
| `src/ii_structure/commands/benchmark_cmd.py` | Create | benchmark group + run/compare commands |
| `src/ii_structure/backends/__init__.py` | Modify | Fix silent KeyError in get_backend |
| `src/ii_structure/output.py` | Modify | Add logging setup |
| `tests/test_graph.py` | Modify | Add tests for file_aux, FTS5, batch fetch, composite index |
| `tests/test_index.py` | Modify | Add tests for parallel build, git ls-files, _process_file |
| `tests/test_migrations.py` | Create | Migration framework tests |
| `tests/test_cli.py` | Modify | Update for split CLI commands |

---

### Task 1: Add logging throughout

**Files:**
- Modify: `src/ii_structure/graph.py`
- Modify: `src/ii_structure/index.py`
- Modify: `src/ii_structure/resolver.py`
- Modify: `src/ii_structure/backends/__init__.py`

- [ ] **Step 1: Add logger to graph.py**

At the top of `src/ii_structure/graph.py`, after the existing imports, add:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Add logger to index.py**

At the top of `src/ii_structure/index.py`, after the existing imports, add:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 3: Add logger to resolver.py**

At the top of `src/ii_structure/resolver.py`, after the existing imports, add:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Add logger to backends/__init__.py**

At the top of `src/ii_structure/backends/__init__.py`, after the existing imports, add:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All 328 tests pass (no behavior change)

- [ ] **Step 6: Commit**

```bash
git add src/ii_structure/graph.py src/ii_structure/index.py src/ii_structure/resolver.py src/ii_structure/backends/__init__.py
git commit -m "chore: add logging infrastructure to core modules"
```

---

### Task 2: Schema migration framework

**Files:**
- Create: `src/ii_structure/migrations.py`
- Create: `tests/test_migrations.py`

- [ ] **Step 1: Write failing tests for migrations**

Create `tests/test_migrations.py`:

```python
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
    # file_aux table should exist
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ii_structure.migrations'`

- [ ] **Step 3: Create migrations.py**

Create `src/ii_structure/migrations.py`:

```python
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
```

- [ ] **Step 4: Run migration tests**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/migrations.py tests/test_migrations.py
git commit -m "feat: add versioned schema migration framework"
```

---

### Task 3: Move file_aux into GraphStore and add SQLite PRAGMAs

**Files:**
- Modify: `src/ii_structure/graph.py`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests for file_aux methods**

Add to `tests/test_graph.py`:

```python
def test_upsert_file_aux(store):
    store.upsert_file_aux("foo.py", '[{"module": "os"}]', None, "abc123")
    aux = store.get_file_aux("foo.py")
    assert aux is not None
    assert aux["imports_json"] == '[{"module": "os"}]'
    assert aux["content_hash"] == "abc123"
    assert aux["parse_error"] is None


def test_get_file_aux_not_found(store):
    assert store.get_file_aux("missing.py") is None


def test_remove_file_aux(store):
    store.upsert_file_aux("foo.py", "[]", None, "abc")
    store.remove_file_aux("foo.py")
    assert store.get_file_aux("foo.py") is None


def test_get_all_file_aux_paths(store):
    store.upsert_file_aux("a.py", "[]", None, "h1")
    store.upsert_file_aux("b.py", "[]", None, "h2")
    paths = store.get_all_file_aux_paths()
    assert set(paths) == {"a.py", "b.py"}


def test_remove_file_data_also_removes_aux(store):
    sym = _make_symbol(name="foo")
    store.store_file_nodes_edges("foo.py", [sym], [], "h1")
    store.upsert_file_aux("foo.py", "[]", None, "h1")
    store.remove_file_data("foo.py")
    assert store.get_file_aux("foo.py") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_graph.py::test_upsert_file_aux -v`
Expected: FAIL — `AttributeError: 'GraphStore' object has no attribute 'upsert_file_aux'`

- [ ] **Step 3: Integrate migrations into GraphStore.__init__ and add file_aux CRUD + PRAGMAs**

In `src/ii_structure/graph.py`, update the `__init__` method to:

```python
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
```

Add these methods to `GraphStore`:

```python
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
```

Update `remove_file_data` to also remove aux:

```python
def remove_file_data(self, file_path: str) -> None:
    self._conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
    self._conn.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))
    self._conn.execute("DELETE FROM file_aux WHERE file_path = ?", (file_path,))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v --tb=short`
Expected: All pass including new file_aux tests

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/graph.py tests/test_graph.py
git commit -m "feat: move file_aux into GraphStore, add SQLite performance PRAGMAs"
```

---

### Task 4: Fix upsert_edge to use INSERT ON CONFLICT

**Files:**
- Modify: `src/ii_structure/graph.py`

- [ ] **Step 1: Replace upsert_edge with ON CONFLICT pattern**

Replace the `upsert_edge` method in `src/ii_structure/graph.py` with:

```python
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
```

**Note:** This requires the composite unique index from migration v3. The `ON CONFLICT` clause references the composite index columns. Since `store_file_nodes_edges` deletes all edges for a file before re-inserting, the conflict path is rarely hit in practice — but this is still correct and 2x faster when it is.

- [ ] **Step 2: Run all edge-related tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v --tb=short`
Expected: All pass

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All 328+ tests pass

- [ ] **Step 4: Commit**

```bash
git add src/ii_structure/graph.py
git commit -m "perf: replace SELECT-then-INSERT in upsert_edge with INSERT ON CONFLICT"
```

---

### Task 5: Add batch node fetching and FTS5 search to GraphStore

**Files:**
- Modify: `src/ii_structure/graph.py`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_graph.py`:

```python
def test_batch_get_nodes(store):
    s1 = _make_symbol(name="alpha", line=1, end_line=3, signature="def alpha():")
    s2 = _make_symbol(name="beta", line=5, end_line=8, signature="def beta():")
    store.store_file_nodes_edges("a.py", [s1, s2], [], "h1")
    qn1 = "a.py::alpha"
    qn2 = "a.py::beta"
    results = store.batch_get_nodes({qn1, qn2})
    assert len(results) == 2
    names = {r["name"] for r in results}
    assert names == {"alpha", "beta"}


def test_batch_get_nodes_empty(store):
    results = store.batch_get_nodes(set())
    assert results == []


def test_rebuild_fts_index(store):
    s1 = _make_symbol(name="parse_file", line=1, end_line=5, signature="def parse_file():")
    store.store_file_nodes_edges("a.py", [s1], [], "h1")
    count = store.rebuild_fts_index()
    assert count == 1


def test_search_fts(store):
    s1 = _make_symbol(name="parse_file", line=1, end_line=5, signature="def parse_file():")
    s2 = _make_symbol(name="load_config", line=6, end_line=10, signature="def load_config():")
    store.store_file_nodes_edges("a.py", [s1, s2], [], "h1")
    store.rebuild_fts_index()
    results = store.search_fts("parse")
    assert len(results) >= 1
    assert results[0]["name"] == "parse_file"


def test_search_fts_no_match(store):
    s1 = _make_symbol(name="foo", line=1, end_line=5, signature="def foo():")
    store.store_file_nodes_edges("a.py", [s1], [], "h1")
    store.rebuild_fts_index()
    results = store.search_fts("zzzznothing")
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_graph.py::test_batch_get_nodes -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Add batch_get_nodes, rebuild_fts_index, and search_fts to GraphStore**

Add to `src/ii_structure/graph.py` in the `GraphStore` class:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v --tb=short`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/graph.py tests/test_graph.py
git commit -m "feat: add batch node fetch, FTS5 search, and rebuild_fts_index to GraphStore"
```

---

### Task 6: Refactor Index to use GraphStore file_aux methods and extract _process_file

**Files:**
- Modify: `src/ii_structure/index.py`

- [ ] **Step 1: Remove _AUX_SCHEMA, _ensure_aux_table, and update _FilesView**

In `src/ii_structure/index.py`:

1. Remove `_AUX_SCHEMA` (lines 18-25) and `_ensure_aux_table` (lines 28-30).
2. Rewrite `_FilesView` to use `self._graph` methods instead of `self._conn`:

```python
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
        # Count distinct files across nodes + aux
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
```

- [ ] **Step 2: Rename _node_to_old_symbol to _node_to_symbol**

Find and replace all occurrences of `_node_to_old_symbol` with `_node_to_symbol` in `src/ii_structure/index.py`.

- [ ] **Step 3: Extract _process_file helper and update build/refresh**

Add this function before the `Index` class:

```python
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
```

Update `Index.build`:

```python
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
```

Update `Index.refresh`:

```python
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
```

- [ ] **Step 4: Update Index.load to remove _ensure_aux_table call**

```python
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
```

- [ ] **Step 5: Remove dead methods: get_symbols, all_symbols, and values from _FilesView**

Remove `Index.get_symbols` (was at line 327), `Index.all_symbols` (was at line 361). The `values` method was already removed from `_FilesView` in step 1.

- [ ] **Step 6: Fix load_or_build_index to narrow exception and log**

```python
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
```

Add `import sqlite3` to the imports at the top of the file.

- [ ] **Step 7: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/ii_structure/index.py
git commit -m "refactor: encapsulate file_aux in GraphStore, extract _process_file, remove dead code"
```

---

### Task 7: Replace search_symbols with FTS5-backed search

**Files:**
- Modify: `src/ii_structure/index.py`

- [ ] **Step 1: Rewrite search_symbols to use FTS5 with LIKE fallback**

Replace the `search_symbols` method on `Index`:

```python
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
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/ii_structure/index.py
git commit -m "perf: replace O(N) search_symbols with indexed SQL lookup"
```

---

### Task 8: Add parallel parsing to build() and refresh()

**Files:**
- Modify: `src/ii_structure/index.py`

- [ ] **Step 1: Add parallel parsing imports and helper**

At the top of `src/ii_structure/index.py`, add:

```python
import concurrent.futures
import os
```

Add a module-level helper for parallel parsing:

```python
_MAX_PARSE_WORKERS = min(os.cpu_count() or 4, 8)


def _parse_file_worker(args: tuple) -> tuple[str, object, str] | None:
    """Parse a single file in a worker process. Returns (rel, ParseResult, content_hash) or None."""
    rel, source_file_str, content = args
    try:
        backend = get_backend(source_file_str)
        result = backend.parse_file(rel, content)
        fhash = _content_hash(content)
        return (rel, result, fhash)
    except Exception as exc:
        logger.warning("Parse failed for %s: %s", rel, exc)
        return None
```

- [ ] **Step 2: Update Index.build to use parallel parsing**

```python
@classmethod
def build(cls, root: pathlib.Path) -> "Index":
    root = root.resolve()
    state_dir = root / ".ii-structure"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_path = state_dir / "graph.db"
    graph = GraphStore(str(db_path))

    gitignore_spec = _load_gitignore(root)
    source_files = _walk_source_files(root, gitignore_spec)

    # Read all files and prepare work items
    work_items = []
    for source_file in source_files:
        rel = str(source_file.relative_to(root))
        try:
            content = source_file.read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning("Skipping %s: %s", rel, exc)
            continue
        work_items.append((rel, str(source_file), content))

    # Parse in parallel, store sequentially
    if len(work_items) > 10:
        with concurrent.futures.ProcessPoolExecutor(max_workers=_MAX_PARSE_WORKERS) as pool:
            parse_results = list(pool.map(_parse_file_worker, work_items))
    else:
        parse_results = [_parse_file_worker(item) for item in work_items]

    for parsed in parse_results:
        if parsed is None:
            continue
        rel, result, fhash = parsed
        graph.store_file_nodes_edges(rel, result.symbols, result.edges, fhash)
        imports_json = json.dumps([asdict(i) for i in result.imports])
        graph.upsert_file_aux(rel, imports_json, result.error, fhash)

    graph.resolve_bare_call_targets()
    graph.rebuild_fts_index()
    graph.set_metadata("project_root", str(root))
    graph.commit()
    return cls(project_root=str(root), graph=graph)
```

- [ ] **Step 3: Update Index.refresh similarly**

```python
def refresh(self, root: pathlib.Path) -> None:
    root = root.resolve()
    gitignore_spec = _load_gitignore(root)
    current_files: set[str] = set()
    existing_files = set(self.graph.get_all_files())
    existing_files.update(self.graph.get_all_file_aux_paths())

    # Collect files that need re-parsing
    work_items = []
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

        work_items.append((rel, str(source_file), content))

    # Parse changed files in parallel, store sequentially
    if len(work_items) > 10:
        with concurrent.futures.ProcessPoolExecutor(max_workers=_MAX_PARSE_WORKERS) as pool:
            parse_results = list(pool.map(_parse_file_worker, work_items))
    else:
        parse_results = [_parse_file_worker(item) for item in work_items]

    for parsed in parse_results:
        if parsed is None:
            continue
        rel, result, fhash = parsed
        self.graph.store_file_nodes_edges(rel, result.symbols, result.edges, fhash)
        imports_json = json.dumps([asdict(i) for i in result.imports])
        self.graph.upsert_file_aux(rel, imports_json, result.error, fhash)

    for old_file in existing_files - current_files:
        self.graph.remove_file_data(old_file)

    self.graph.resolve_bare_call_targets()
    self.graph.rebuild_fts_index()
    self.graph.commit()
    self._invalidate_cache()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/index.py
git commit -m "perf: add parallel file parsing using ProcessPoolExecutor"
```

---

### Task 9: Use git ls-files for file discovery

**Files:**
- Modify: `src/ii_structure/index.py`
- Modify: `tests/test_index.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_index.py`:

```python
import subprocess


def test_git_ls_files_used_in_git_repo(tmp_path):
    """In a git repo, _walk_source_files should use git ls-files."""
    # Create a git repo with one tracked and one untracked file
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True,
    )
    tracked = tmp_path / "tracked.py"
    tracked.write_text("x = 1")
    untracked = tmp_path / "untracked.py"
    untracked.write_text("y = 2")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

    from ii_structure.index import _walk_source_files
    files = _walk_source_files(tmp_path, None)
    names = [f.name for f in files]
    assert "tracked.py" in names
    assert "untracked.py" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_index.py::test_git_ls_files_used_in_git_repo -v`
Expected: FAIL — `untracked.py` is included

- [ ] **Step 3: Update _walk_source_files to try git ls-files first**

Replace `_walk_source_files` in `src/ii_structure/index.py`:

```python
def _walk_source_files(
    root: pathlib.Path,
    gitignore_spec: pathspec.PathSpec | None,
) -> list[pathlib.Path]:
    import subprocess

    extensions = supported_extensions()

    # Try git ls-files first (faster, respects .gitignore natively)
    if (root / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                files = []
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    path = root / line
                    if path.suffix not in extensions:
                        continue
                    parts = pathlib.PurePosixPath(line).parts
                    if any(part in SKIP_DIRS for part in parts):
                        continue
                    if path.is_file():
                        files.append(path)
                return sorted(files)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("git ls-files failed, falling back to rglob: %s", exc)

    # Fallback: walk filesystem
    files = []
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_index.py -v --tb=short`
Expected: All pass

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ii_structure/index.py tests/test_index.py
git commit -m "perf: use git ls-files for file discovery when in a git repo"
```

---

### Task 10: Fix get_backend silent KeyError

**Files:**
- Modify: `src/ii_structure/backends/__init__.py`

- [ ] **Step 1: Add else clause with explicit error**

In `src/ii_structure/backends/__init__.py`, update `get_backend`:

```python
def get_backend(file_path: str) -> LanguageBackend:
    """Get the appropriate backend for a file based on its extension."""
    ext = pathlib.Path(file_path).suffix
    lang = LANGUAGE_EXTENSIONS.get(ext)

    if lang is None:
        raise ValueError(f"Unsupported file type: {ext}")

    if lang not in _backends:
        if lang == "python":
            from ii_structure.backends.python import PythonBackend
            _backends[lang] = PythonBackend()
        elif lang == "go":
            from ii_structure.backends.golang import GoBackend
            _backends[lang] = GoBackend()
        elif lang == "typescript":
            from ii_structure.backends.typescript import TypeScriptBackend
            _backends[lang] = TypeScriptBackend()
        else:
            raise ValueError(f"No backend registered for language: {lang}")

    return _backends[lang]
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/ii_structure/backends/__init__.py
git commit -m "fix: add explicit error for unregistered language backends"
```

---

### Task 11: Clean up resolver.py

**Files:**
- Modify: `src/ii_structure/resolver.py`

- [ ] **Step 1: Remove try/except on jedi import**

Replace the import section:

```python
import logging
import pathlib

import jedi

from ii_structure.index import Index

logger = logging.getLogger(__name__)
```

Remove the `if jedi is not None:` check in `get_definition_source` — just use `jedi` directly since it's a hard dependency in pyproject.toml.

```python
def get_definition_source(
    project_root: str,
    name: str,
    index: Index,
    file_hint: str | None = None,
) -> dict | None:
    root = pathlib.Path(project_root)

    candidates = index.search_symbols(name)
    if not candidates:
        return None

    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]
        if not candidates:
            return None

    if len(candidates) == 1:
        return _read_symbol_source(root, candidates[0])

    # Multiple candidates — use Jedi to resolve
    project = jedi.Project(path=str(root))
    for candidate in candidates:
        file_path = root / candidate["file"]
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8", errors="replace")
        script = jedi.Script(source, path=str(file_path), project=project)
        try:
            defs = script.goto(line=candidate["line"], column=len("def "))
            if defs:
                return _read_symbol_source(root, candidate)
        except Exception:
            continue

    return _read_symbol_source(root, candidates[0])
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/ii_structure/resolver.py
git commit -m "cleanup: remove unnecessary try/except on jedi import"
```

---

### Task 12: Split CLI — move init and benchmark commands

**Files:**
- Create: `src/ii_structure/commands/init_cmd.py`
- Create: `src/ii_structure/commands/benchmark_cmd.py`
- Modify: `src/ii_structure/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Create init_cmd.py**

Create `src/ii_structure/commands/init_cmd.py`. Move `CLAUDE_MD_SECTION`, `MARKER`, and the `init` function from `cli.py`:

```python
"""Init command — adds ii-structure instructions to CLAUDE.md."""
import pathlib

import click

CLAUDE_MD_SECTION = """<paste the full CLAUDE_MD_SECTION string from cli.py here>"""

MARKER = "# ii-structure — MANDATORY for Code Navigation and Editing"


def register(cli_group):
    """Register the init command on the given CLI group."""

    @cli_group.command()
    @click.pass_context
    def init(ctx):
        """Add ii-structure instructions to CLAUDE.md for this project."""
        root = ctx.obj["root"]
        claude_md = root / "CLAUDE.md"

        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8")
            if MARKER in content:
                click.echo("CLAUDE.md already contains ii-structure section — skipping.")
                return
            updated = content.rstrip() + "\n\n" + CLAUDE_MD_SECTION + "\n"
            claude_md.write_text(updated, encoding="utf-8")
            click.echo("Appended ii-structure section to existing CLAUDE.md")
        else:
            claude_md.write_text(CLAUDE_MD_SECTION + "\n", encoding="utf-8")
            click.echo(f"Created CLAUDE.md with ii-structure instructions at {claude_md}")
```

- [ ] **Step 2: Create benchmark_cmd.py**

Create `src/ii_structure/commands/benchmark_cmd.py`. Move `benchmark`, `benchmark_run`, and `benchmark_compare` from `cli.py`:

```python
"""Benchmark commands for ii-structure."""
import json
import pathlib
import sys

import click
import yaml

from ii_structure.index import load_or_build_index
from ii_structure.output import format_success, format_error


def register(cli_group):
    """Register the benchmark command group on the given CLI group."""

    @cli_group.group()
    def benchmark():
        """Run benchmarks."""
        pass

    @benchmark.command(name="run")
    @click.option("--query", default=None, help="Run a single query by ID")
    @click.pass_context
    def benchmark_run(ctx, query):
        """Run benchmark queries and report results."""
        root = ctx.obj["root"]
        queries_dir = root / "benchmarks" / "queries"

        if not queries_dir.exists():
            click.echo(format_error("benchmark", f"No queries directory at {queries_dir}"))
            sys.exit(1)

        try:
            from benchmarks.runner import (
                load_queries, run_benchmark, format_report,
                save_baseline, run_query,
            )
        except ImportError:
            click.echo(format_error("benchmark", "benchmarks module not found"))
            sys.exit(1)

        if query:
            queries = load_queries(queries_dir)
            matched = [q for q in queries if q.get("id") == query]
            if not matched:
                click.echo(format_error("benchmark", f"Query '{query}' not found"))
                sys.exit(1)
            result = run_query(matched[0], str(root))
            click.echo(yaml.dump(result, default_flow_style=False))
            return

        results = run_benchmark(str(root), queries_dir)
        report = format_report(results)
        click.echo(report)

        baselines_dir = root / "benchmarks" / "baselines"
        baselines_dir.mkdir(parents=True, exist_ok=True)
        saved = save_baseline(results, baselines_dir)
        click.echo(f"\nBaseline saved to {saved}")

    @benchmark.command(name="compare")
    @click.argument("baseline_file", type=click.Path(exists=True))
    @click.pass_context
    def benchmark_compare(ctx, baseline_file):
        """Compare current results against a baseline."""
        root = ctx.obj["root"]
        queries_dir = root / "benchmarks" / "queries"

        try:
            from benchmarks.runner import (
                load_queries, run_benchmark, compare_baselines,
            )
        except ImportError:
            click.echo(format_error("benchmark", "benchmarks module not found"))
            sys.exit(1)

        current = run_benchmark(str(root), queries_dir)
        with open(baseline_file) as f:
            baseline = json.load(f)

        report = compare_baselines(current, baseline)
        click.echo(report)
```

- [ ] **Step 3: Update cli.py to import from new modules**

Remove `CLAUDE_MD_SECTION`, `MARKER`, `init`, `benchmark`, `benchmark_run`, `benchmark_compare` from `src/ii_structure/cli.py`.

Add at the bottom of `cli.py`, before `def main()`:

```python
# Register split-out commands
from ii_structure.commands import init_cmd, benchmark_cmd
init_cmd.register(cli)
benchmark_cmd.register(cli)
```

- [ ] **Step 4: Run CLI tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v --tb=short`
Expected: All pass (init and benchmark tests should still work)

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ii_structure/commands/init_cmd.py src/ii_structure/commands/benchmark_cmd.py src/ii_structure/cli.py
git commit -m "refactor: split init and benchmark commands out of cli.py"
```

---

### Task 13: Remove dead code from GraphStore

**Files:**
- Modify: `src/ii_structure/graph.py`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Remove GraphStore.get_edges_by_source**

Remove the `get_edges_by_source` method from `src/ii_structure/graph.py` (was at line 258). Verify no callers:

Run: `.venv/bin/python -c "import subprocess; subprocess.run(['grep', '-rn', 'get_edges_by_source', 'src/'])"`

- [ ] **Step 2: Check if search_nodes is used anywhere outside tests**

Run: `.venv/bin/python -c "import subprocess; subprocess.run(['grep', '-rn', 'search_nodes', 'src/'])"`

If only used in `graph.py` definition, remove it. If used in commands, keep it.

**Note:** `search_nodes` is now superseded by `search_fts` — remove it.

- [ ] **Step 3: Remove any tests that reference removed methods**

Update `tests/test_graph.py`: remove `test_search_nodes` and `test_search_nodes_no_match` if they reference the removed `search_nodes` method. These are replaced by the FTS tests from Task 5.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/graph.py tests/test_graph.py
git commit -m "cleanup: remove dead GraphStore methods (get_edges_by_source, search_nodes)"
```

---

### Task 14: Document bidirectional blast radius and add batch fetch

**Files:**
- Modify: `src/ii_structure/graph.py`

- [ ] **Step 1: Add docstring clarifying bidirectional intent**

Update the `get_impact_radius` docstring:

```python
def get_impact_radius(
    self,
    qualified_name: str,
    max_depth: int = 3,
    max_nodes: int = 200,
) -> dict[str, Any]:
    """Blast radius via recursive CTE.

    Walks both directions intentionally: callers (who depends on this?)
    AND callees (what does this depend on?) are both part of the impact
    surface. A change can break callers AND can be affected by changes
    to its own dependencies.
    """
```

- [ ] **Step 2: Replace per-node get_node calls with batch_get_nodes**

In the same method, replace the loop that calls `self.get_node(qn)` individually:

```python
# OLD (N+1 queries):
# for row in rows:
#     node = self.get_node(qn)

# NEW (batch):
impacted_qns = {r["node_qn"] for r in rows if r["node_qn"] != qualified_name}
batch_results = self.batch_get_nodes(impacted_qns)

impacted_nodes: list[dict[str, Any]] = []
impacted_files: set[str] = set()

# Build depth map
depth_map = {r["node_qn"]: r["min_depth"] for r in rows}

for node in batch_results:
    qn = node["qualified_name"]
    node["depth"] = depth_map.get(qn, 0)
    impacted_nodes.append(node)
    impacted_files.add(node["file_path"])
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py tests/test_commands/test_blast_radius.py -v --tb=short`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/ii_structure/graph.py
git commit -m "perf: batch node fetch in blast radius, document bidirectional traversal"
```

---

### Task 15: Convert get_transitive_tests to recursive CTE

**Files:**
- Modify: `src/ii_structure/graph.py`

- [ ] **Step 1: Rewrite get_transitive_tests**

Replace the BFS Python loop with a SQL recursive CTE:

```python
def get_transitive_tests(
    self, qualified_name: str, max_depth: int = 2
) -> list[dict[str, Any]]:
    """Find test coverage (direct and transitive) via recursive CTE."""
    # Direct TESTED_BY
    direct_rows = self._conn.execute(
        "SELECT source_qualified FROM edges WHERE kind = 'TESTED_BY' AND target_qualified = ?",
        (qualified_name,),
    ).fetchall()

    test_qns: dict[str, bool] = {}  # qn -> indirect
    for row in direct_rows:
        test_qns[row[0]] = False

    # Transitive: find callers via CTE, then their TESTED_BY edges
    if max_depth > 0:
        cte_rows = self._conn.execute(
            """\
            WITH RECURSIVE callers(qn, depth) AS (
                SELECT ?, 0
                UNION
                SELECT e.source_qualified, c.depth + 1
                FROM callers c JOIN edges e ON e.target_qualified = c.qn
                WHERE e.kind = 'CALLS' AND c.depth < ?
            )
            SELECT DISTINCT e.source_qualified
            FROM callers c
            JOIN edges e ON e.target_qualified = c.qn
            WHERE e.kind = 'TESTED_BY' AND c.depth > 0
            """,
            (qualified_name, max_depth),
        ).fetchall()
        for row in cte_rows:
            if row[0] not in test_qns:
                test_qns[row[0]] = True

    if not test_qns:
        return []

    # Batch fetch test nodes
    batch = self.batch_get_nodes(set(test_qns.keys()))
    tests: list[dict[str, Any]] = []
    for node in batch:
        node["indirect"] = test_qns.get(node["qualified_name"], True)
        tests.append(node)
    return tests
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py tests/test_commands/test_test_coverage.py -v --tb=short`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add src/ii_structure/graph.py
git commit -m "perf: replace N+1 BFS in get_transitive_tests with recursive CTE"
```

---

### Task 16: Final integration test run

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Run ii-structure against itself**

```bash
cd /Users/somen/Projects/ii-structure
ii-structure files --summary | head -30
ii-structure search parse_file
ii-structure dead-code
ii-structure blast-radius GraphStore
```

Verify all commands still work correctly.

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: integration fixups from full test run"
```
