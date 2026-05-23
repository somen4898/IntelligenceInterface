# Graph Persistence & Blast Radius Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ii-structure's JSON index with a SQLite graph store that persists symbol relationships (calls, imports, test coverage), enabling instant `usages`/`imports` queries and new `blast-radius`/`dead-code`/`test-coverage` commands.

**Architecture:** SQLite replaces `index.json`. Nodes table stores symbols (what JSON stores today). Edges table stores relationships extracted from AST at build time. All existing commands continue working with the same public API. Three new analysis commands query the edge graph.

**Tech Stack:** Python 3.10+, sqlite3 (stdlib), tree-sitter (existing), ast (existing). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-22-graph-persistence-design.md`

**Reference implementation:** `/tmp/code-review-graph/` (clone of code-review-graph for studying patterns)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/ii_structure/graph.py` | CREATE | GraphStore class — SQLite schema, CRUD, queries, blast radius CTE |
| `src/ii_structure/parser.py` | MODIFY | Add EdgeInfo dataclass, add `_extract_calls()` for Python call extraction |
| `src/ii_structure/backends/golang.py` | MODIFY | Add call extraction to GoBackend.parse_file |
| `src/ii_structure/backends/typescript.py` | MODIFY | Add call extraction to TypeScriptBackend.parse_file |
| `src/ii_structure/backends/base.py` | MODIFY | Remove `find_usages` from Protocol, keep `parse_file` and `get_definition_source` |
| `src/ii_structure/index.py` | REWRITE | Thin wrapper around GraphStore, same public API |
| `src/ii_structure/commands/usages.py` | REWRITE | SQL edge query instead of LSP dispatch |
| `src/ii_structure/commands/imports.py` | REWRITE | SQL edge query, remove 7 helper functions |
| `src/ii_structure/commands/blast_radius.py` | CREATE | New command — recursive CTE impact analysis |
| `src/ii_structure/commands/dead_code.py` | CREATE | New command — uncalled symbols |
| `src/ii_structure/commands/test_coverage.py` | CREATE | New command — structural test coverage |
| `src/ii_structure/commands/body.py` | MODIFY | Use GraphStore for node lookup |
| `src/ii_structure/commands/replace_body.py` | MODIFY | Refresh edges after write |
| `src/ii_structure/commands/insert_symbol.py` | MODIFY | Refresh edges after write |
| `src/ii_structure/resolver.py` | MODIFY | Remove `find_usages` and its helpers, keep `get_definition_source` and `_read_symbol_source` |
| `src/ii_structure/cli.py` | MODIFY | Add 3 new Click commands, update CLAUDE_MD_SECTION |
| `src/ii_structure/help_content.yaml` | MODIFY | Add entries for 3 new commands |
| `tests/test_graph.py` | CREATE | GraphStore unit tests |
| `tests/test_edge_extraction.py` | CREATE | Edge extraction tests per language |
| `tests/test_commands/test_blast_radius.py` | CREATE | Blast radius command tests |
| `tests/test_commands/test_dead_code.py` | CREATE | Dead code command tests |
| `tests/test_commands/test_test_coverage.py` | CREATE | Test coverage command tests |

---

## Task 1: GraphStore — Schema and CRUD

**Files:**
- Create: `src/ii_structure/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests for GraphStore creation and schema**

```python
# tests/test_graph.py
import sqlite3
import pytest
from ii_structure.graph import GraphStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "graph.db"
    with GraphStore(db_path) as s:
        yield s


def test_creates_db_file(tmp_path):
    db_path = tmp_path / "graph.db"
    store = GraphStore(db_path)
    assert db_path.exists()
    store.close()


def test_schema_has_tables(store):
    conn = store._conn
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "nodes" in tables
    assert "edges" in tables
    assert "metadata" in tables


def test_wal_mode_enabled(store):
    mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_schema_version_set(store):
    row = store._conn.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    ).fetchone()
    assert row is not None
    assert int(row[0]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ii_structure.graph'`

- [ ] **Step 3: Implement GraphStore — schema init, pragmas, lifecycle**

```python
# src/ii_structure/graph.py
"""SQLite-backed code knowledge graph."""
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_SCHEMA_SQL = """
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

SCHEMA_VERSION = 1


def _sanitize_name(s: str, max_len: int = 256) -> str:
    """Strip control chars and truncate to prevent prompt injection."""
    cleaned = "".join(
        ch for ch in s if ch in ("\t", "\n") or ord(ch) >= 0x20
    )
    return cleaned[:max_len]


class GraphStore:
    """SQLite-backed code knowledge graph."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path), timeout=30, check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA_SQL)
        # Set schema version if fresh DB
        existing = self._conn.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        if not existing:
            self._conn.execute(
                "INSERT INTO metadata (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self._conn:
            self._conn.commit()
            self._conn.close()

    def commit(self) -> None:
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: 4 PASS

- [ ] **Step 5: Write failing tests for node CRUD**

Add to `tests/test_graph.py`:

```python
from ii_structure.parser import SymbolInfo


def _make_symbol(name="save", kind="method", line=10, end_line=15,
                 parent="User", file_path="models.py"):
    return SymbolInfo(
        name=name, kind=kind, line=line, end_line=end_line,
        signature=f"def {name}(self)", docstring=None,
        parent=parent, children=[], decorators=[],
    )


def test_upsert_node(store):
    sym = _make_symbol()
    node_id = store.upsert_node(sym, "models.py", file_hash="abc123")
    assert node_id > 0


def test_get_node(store):
    sym = _make_symbol()
    store.upsert_node(sym, "models.py")
    store.commit()
    node = store.get_node("models.py::User.save")
    assert node is not None
    assert node["name"] == "save"
    assert node["kind"] == "method"


def test_get_node_not_found(store):
    assert store.get_node("nonexistent") is None


def test_get_nodes_by_file(store):
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("delete", parent="User"), "models.py")
    store.upsert_node(_make_symbol("helper", kind="function", parent=None), "utils.py")
    store.commit()
    nodes = store.get_nodes_by_file("models.py")
    assert len(nodes) == 2


def test_upsert_node_updates_existing(store):
    sym = _make_symbol(line=10)
    store.upsert_node(sym, "models.py")
    sym2 = _make_symbol(line=20)
    store.upsert_node(sym2, "models.py")
    store.commit()
    node = store.get_node("models.py::User.save")
    assert node["line_start"] == 20


def test_remove_file_data(store):
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("helper", kind="function", parent=None), "utils.py")
    store.commit()
    store.remove_file_data("models.py")
    store.commit()
    assert store.get_nodes_by_file("models.py") == []
    assert len(store.get_nodes_by_file("utils.py")) == 1
```

- [ ] **Step 6: Implement upsert_node, get_node, get_nodes_by_file, remove_file_data**

Add to `GraphStore` class in `src/ii_structure/graph.py`:

```python
    def _make_qualified(self, name: str, file_path: str, parent: str | None) -> str:
        name = _sanitize_name(name)
        if parent:
            return f"{file_path}::{_sanitize_name(parent)}.{name}"
        return f"{file_path}::{name}"

    def upsert_node(self, symbol: "SymbolInfo", file_path: str,
                    file_hash: str = "") -> int:
        """Insert or update a node. Returns the node ID."""
        now = time.time()
        qualified = self._make_qualified(symbol.name, file_path, symbol.parent)
        decorators = json.dumps(symbol.decorators) if symbol.decorators else "[]"
        children = json.dumps(symbol.children) if symbol.children else "[]"
        docstring = symbol.docstring[:200] if symbol.docstring else None

        self._conn.execute(
            """INSERT INTO nodes
               (kind, name, qualified_name, file_path, line_start, line_end,
                signature, docstring, parent_name, decorators, children,
                file_hash, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(qualified_name) DO UPDATE SET
                 kind=excluded.kind, name=excluded.name,
                 file_path=excluded.file_path, line_start=excluded.line_start,
                 line_end=excluded.line_end, signature=excluded.signature,
                 docstring=excluded.docstring, parent_name=excluded.parent_name,
                 decorators=excluded.decorators, children=excluded.children,
                 file_hash=excluded.file_hash, updated_at=excluded.updated_at
            """,
            (symbol.kind, symbol.name, qualified, file_path,
             symbol.line, symbol.end_line, symbol.signature,
             docstring, symbol.parent, decorators, children,
             file_hash, now),
        )
        row = self._conn.execute(
            "SELECT id FROM nodes WHERE qualified_name = ?", (qualified,)
        ).fetchone()
        return row["id"]

    def get_node(self, qualified_name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE qualified_name = ?", (qualified_name,)
        ).fetchone()
        return dict(row) if row else None

    def get_nodes_by_file(self, file_path: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE file_path = ?", (file_path,)
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_file_data(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: 10 PASS

- [ ] **Step 8: Write failing tests for edge CRUD**

Add to `tests/test_graph.py`:

```python
def test_upsert_edge(store):
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("create", parent="UserService"), "services.py")
    store.commit()
    edge_id = store.upsert_edge(
        kind="CALLS",
        source_qualified="services.py::UserService.create",
        target_qualified="models.py::User.save",
        file_path="services.py",
        line=18,
    )
    assert edge_id > 0


def test_get_edges_by_target(store):
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("create", parent="UserService"), "services.py")
    store.upsert_edge(
        kind="CALLS",
        source_qualified="services.py::UserService.create",
        target_qualified="models.py::User.save",
        file_path="services.py", line=18,
    )
    store.commit()
    edges = store.get_edges_by_target("models.py::User.save")
    assert len(edges) == 1
    assert edges[0]["source_qualified"] == "services.py::UserService.create"


def test_get_edges_by_source(store):
    store.upsert_edge(
        kind="CALLS",
        source_qualified="services.py::UserService.create",
        target_qualified="models.py::User.save",
        file_path="services.py", line=18,
    )
    store.upsert_edge(
        kind="CALLS",
        source_qualified="services.py::UserService.create",
        target_qualified="models.py::User.__init__",
        file_path="services.py", line=15,
    )
    store.commit()
    edges = store.get_edges_by_source("services.py::UserService.create")
    assert len(edges) == 2


def test_remove_file_data_removes_edges(store):
    store.upsert_edge(
        kind="CALLS",
        source_qualified="services.py::UserService.create",
        target_qualified="models.py::User.save",
        file_path="services.py", line=18,
    )
    store.commit()
    store.remove_file_data("services.py")
    store.commit()
    edges = store.get_edges_by_source("services.py::UserService.create")
    assert len(edges) == 0


def test_store_file_nodes_edges_atomic(store):
    """Atomic replace: old data removed, new data inserted."""
    store.upsert_node(_make_symbol("old_func", kind="function", parent=None), "app.py")
    store.upsert_edge(
        kind="CALLS", source_qualified="app.py::old_func",
        target_qualified="models.py::User.save", file_path="app.py", line=5,
    )
    store.commit()

    from ii_structure.parser import SymbolInfo
    new_symbols = [_make_symbol("new_func", kind="function", parent=None)]
    new_edges = [("CALLS", "app.py::new_func", "models.py::User.delete", "app.py", 10)]

    store.store_file_nodes_edges("app.py", new_symbols, new_edges, "newhash")

    nodes = store.get_nodes_by_file("app.py")
    assert len(nodes) == 1
    assert nodes[0]["name"] == "new_func"
    edges = store.get_edges_by_source("app.py::new_func")
    assert len(edges) == 1
```

- [ ] **Step 9: Implement upsert_edge, get_edges_by_source/target, store_file_nodes_edges**

Add to `GraphStore` class:

```python
    def upsert_edge(self, kind: str, source_qualified: str,
                    target_qualified: str, file_path: str,
                    line: int = 0) -> int:
        """Insert or update an edge. Returns the edge ID."""
        now = time.time()
        existing = self._conn.execute(
            """SELECT id FROM edges
               WHERE kind=? AND source_qualified=? AND target_qualified=?
                     AND file_path=? AND line=?""",
            (kind, source_qualified, target_qualified, file_path, line),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE edges SET updated_at=? WHERE id=?",
                (now, existing["id"]),
            )
            return existing["id"]
        self._conn.execute(
            """INSERT INTO edges
               (kind, source_qualified, target_qualified, file_path, line, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, source_qualified, target_qualified, file_path, line, now),
        )
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_edges_by_source(self, qualified_name: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE source_qualified = ?", (qualified_name,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges_by_target(self, qualified_name: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE target_qualified = ?", (qualified_name,)
        ).fetchall()
        return [dict(r) for r in rows]

    def store_file_nodes_edges(self, file_path: str,
                                symbols: list, edges: list,
                                file_hash: str = "") -> None:
        """Atomically replace all nodes/edges for a file."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self.remove_file_data(file_path)
            for sym in symbols:
                self.upsert_node(sym, file_path, file_hash=file_hash)
            for edge in edges:
                if isinstance(edge, tuple):
                    kind, src, tgt, fp, ln = edge
                    self.upsert_edge(kind, src, tgt, fp, ln)
                else:
                    self.upsert_edge(
                        edge.kind, edge.source, edge.target,
                        edge.file_path, edge.line,
                    )
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: 14 PASS

- [ ] **Step 11: Commit**

```bash
git add src/ii_structure/graph.py tests/test_graph.py
git commit -m "feat: GraphStore with SQLite schema, node/edge CRUD, atomic file replace"
```

---

## Task 2: GraphStore — Analysis Queries (blast radius, dead code, test coverage)

**Files:**
- Modify: `src/ii_structure/graph.py`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests for blast radius**

Add to `tests/test_graph.py`:

```python
def _build_chain(store):
    """A -> B -> C linear call chain."""
    for name, fp in [("A", "a.py"), ("B", "b.py"), ("C", "c.py")]:
        store.upsert_node(_make_symbol(name, kind="function", parent=None), fp)
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 5)
    store.upsert_edge("CALLS", "b.py::B", "c.py::C", "b.py", 10)
    store.commit()


def test_blast_radius_direct(store):
    _build_chain(store)
    result = store.get_impact_radius("c.py::C", max_depth=1)
    affected_qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "b.py::B" in affected_qns  # B calls C


def test_blast_radius_transitive(store):
    _build_chain(store)
    result = store.get_impact_radius("c.py::C", max_depth=3)
    affected_qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "b.py::B" in affected_qns
    assert "a.py::A" in affected_qns  # A calls B which calls C


def test_blast_radius_depth_limit(store):
    _build_chain(store)
    result = store.get_impact_radius("c.py::C", max_depth=1)
    affected_qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "b.py::B" in affected_qns
    assert "a.py::A" not in affected_qns  # depth 1 only reaches B


def test_blast_radius_diamond(store):
    """A -> C, B -> C. Changing C affects both A and B."""
    for name, fp in [("A", "a.py"), ("B", "b.py"), ("C", "c.py")]:
        store.upsert_node(_make_symbol(name, kind="function", parent=None), fp)
    store.upsert_edge("CALLS", "a.py::A", "c.py::C", "a.py", 5)
    store.upsert_edge("CALLS", "b.py::B", "c.py::C", "b.py", 10)
    store.commit()
    result = store.get_impact_radius("c.py::C", max_depth=2)
    affected_qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "a.py::A" in affected_qns
    assert "b.py::B" in affected_qns


def test_blast_radius_cycle(store):
    """A -> B -> A. Should not infinite loop."""
    for name, fp in [("A", "a.py"), ("B", "b.py")]:
        store.upsert_node(_make_symbol(name, kind="function", parent=None), fp)
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 5)
    store.upsert_edge("CALLS", "b.py::B", "a.py::A", "b.py", 10)
    store.commit()
    result = store.get_impact_radius("a.py::A", max_depth=5)
    # Should return both without hanging
    assert len(result["impacted_nodes"]) >= 1


def test_blast_radius_empty(store):
    store.upsert_node(_make_symbol("lonely", kind="function", parent=None), "solo.py")
    store.commit()
    result = store.get_impact_radius("solo.py::lonely", max_depth=3)
    assert result["impacted_nodes"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_graph.py -k "blast_radius" -v`
Expected: FAIL — `AttributeError: 'GraphStore' object has no attribute 'get_impact_radius'`

- [ ] **Step 3: Implement get_impact_radius using recursive CTE**

Add to `GraphStore` class:

```python
    def get_impact_radius(self, qualified_name: str,
                          max_depth: int = 3,
                          max_nodes: int = 200) -> dict:
        """BFS from a symbol to find all impacted nodes within depth N."""
        seed = self.get_node(qualified_name)
        if not seed:
            return {
                "changed_node": None,
                "impacted_nodes": [],
                "impacted_files": [],
                "total_impacted": 0,
            }

        # Use temp table for seed set
        self._conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _impact_seeds (qn TEXT PRIMARY KEY)"
        )
        self._conn.execute("DELETE FROM _impact_seeds")
        self._conn.execute(
            "INSERT OR IGNORE INTO _impact_seeds (qn) VALUES (?)",
            (qualified_name,),
        )

        cte_sql = """
        WITH RECURSIVE impacted(node_qn, depth) AS (
            SELECT qn, 0 FROM _impact_seeds
            UNION
            SELECT e.source_qualified, i.depth + 1
            FROM impacted i
            JOIN edges e ON e.target_qualified = i.node_qn
            WHERE i.depth < ?
            UNION
            SELECT e.target_qualified, i.depth + 1
            FROM impacted i
            JOIN edges e ON e.source_qualified = i.node_qn
            WHERE i.depth < ?
        )
        SELECT DISTINCT node_qn, MIN(depth) AS min_depth
        FROM impacted
        GROUP BY node_qn
        LIMIT ?
        """
        rows = self._conn.execute(
            cte_sql, (max_depth, max_depth, max_nodes + 1),
        ).fetchall()

        impacted_nodes = []
        for r in rows:
            qn = r["node_qn"]
            if qn == qualified_name:
                continue
            node = self.get_node(qn)
            if node:
                node["depth"] = r["min_depth"]
                impacted_nodes.append(node)

        impacted_files = list({n["file_path"] for n in impacted_nodes})

        return {
            "changed_node": dict(seed),
            "impacted_nodes": impacted_nodes,
            "impacted_files": impacted_files,
            "total_impacted": len(impacted_nodes),
        }
```

- [ ] **Step 4: Run blast radius tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -k "blast_radius" -v`
Expected: 6 PASS

- [ ] **Step 5: Write failing tests for dead code and test coverage**

Add to `tests/test_graph.py`:

```python
def test_get_dead_symbols(store):
    store.upsert_node(_make_symbol("used_func", kind="function", parent=None), "app.py")
    store.upsert_node(_make_symbol("dead_func", kind="function", parent=None), "app.py")
    store.upsert_edge("CALLS", "app.py::used_func", "app.py::dead_func", "app.py", 5)
    store.commit()
    # dead_func is called, used_func is NOT called by anyone
    dead = store.get_dead_symbols()
    dead_names = {d["name"] for d in dead}
    assert "used_func" in dead_names  # no one calls used_func
    assert "dead_func" not in dead_names  # dead_func IS called


def test_dead_code_excludes_tests(store):
    store.upsert_node(
        _make_symbol("test_something", kind="function", parent=None), "test_app.py"
    )
    store.commit()
    dead = store.get_dead_symbols()
    dead_names = {d["name"] for d in dead}
    assert "test_something" not in dead_names  # test functions excluded


def test_dead_code_excludes_init_main(store):
    store.upsert_node(_make_symbol("__init__", kind="method", parent="User"), "models.py")
    store.upsert_node(_make_symbol("main", kind="function", parent=None), "cli.py")
    store.commit()
    dead = store.get_dead_symbols()
    dead_names = {d["name"] for d in dead}
    assert "__init__" not in dead_names
    assert "main" not in dead_names


def test_get_transitive_tests_direct(store):
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(
        _make_symbol("test_save", kind="function", parent=None), "test_models.py"
    )
    store.upsert_edge(
        "TESTED_BY", "test_models.py::test_save",
        "models.py::User.save", "test_models.py", 10,
    )
    store.commit()
    tests = store.get_transitive_tests("models.py::User.save")
    assert len(tests) == 1
    assert tests[0]["name"] == "test_save"
    assert tests[0]["indirect"] is False


def test_get_transitive_tests_indirect(store):
    """test_create calls create, create calls save. save is indirectly tested."""
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("create", parent="UserService"), "services.py")
    store.upsert_node(
        _make_symbol("test_create", kind="function", parent=None), "test_svc.py"
    )
    store.upsert_edge("CALLS", "services.py::UserService.create",
                      "models.py::User.save", "services.py", 15)
    store.upsert_edge("TESTED_BY", "test_svc.py::test_create",
                      "services.py::UserService.create", "test_svc.py", 10)
    store.commit()
    tests = store.get_transitive_tests("models.py::User.save", max_depth=2)
    assert len(tests) == 1
    assert tests[0]["name"] == "test_create"
    assert tests[0]["indirect"] is True
```

- [ ] **Step 6: Implement get_dead_symbols and get_transitive_tests**

Add to `GraphStore` class:

```python
    _ENTRY_POINT_NAMES = {"main", "__main__", "__init__", "setup", "teardown"}

    def get_dead_symbols(self, file_path: str | None = None) -> list[dict]:
        """Find symbols with zero incoming CALLS edges."""
        where = "WHERE n.kind IN ('function', 'method')"
        params: list = []
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
        rows = self._conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            # Exclude test functions, entry points
            if d["name"].startswith("test_") or d["name"] in self._ENTRY_POINT_NAMES:
                continue
            if d["file_path"].startswith("test_") or "/test_" in d["file_path"]:
                continue
            results.append(d)
        return results

    def get_transitive_tests(self, qualified_name: str,
                             max_depth: int = 2) -> list[dict]:
        """Find tests covering a node, including indirect coverage."""
        results: list[dict] = []
        seen: set[str] = set()

        # Direct TESTED_BY
        for row in self._conn.execute(
            "SELECT source_qualified FROM edges "
            "WHERE target_qualified = ? AND kind = 'TESTED_BY'",
            (qualified_name,),
        ).fetchall():
            src = row["source_qualified"]
            if src not in seen:
                seen.add(src)
                node = self.get_node(src)
                if node:
                    node["indirect"] = False
                    results.append(node)

        # Transitive: who calls this symbol? Do they have tests?
        frontier = {qualified_name}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for qn in frontier:
                for row in self._conn.execute(
                    "SELECT source_qualified FROM edges "
                    "WHERE target_qualified = ? AND kind = 'CALLS'",
                    (qn,),
                ).fetchall():
                    next_frontier.add(row["source_qualified"])
            for caller in next_frontier:
                for row in self._conn.execute(
                    "SELECT source_qualified FROM edges "
                    "WHERE target_qualified = ? AND kind = 'TESTED_BY'",
                    (caller,),
                ).fetchall():
                    src = row["source_qualified"]
                    if src not in seen:
                        seen.add(src)
                        node = self.get_node(src)
                        if node:
                            node["indirect"] = True
                            results.append(node)
            frontier = next_frontier

        return results
```

- [ ] **Step 7: Run all GraphStore tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: All PASS (19 tests)

- [ ] **Step 8: Write failing tests for search_nodes and get_all_files**

Add to `tests/test_graph.py`:

```python
def test_search_nodes(store):
    store.upsert_node(_make_symbol("authenticate_user", kind="function", parent=None), "auth.py")
    store.upsert_node(_make_symbol("validate_email", kind="function", parent=None), "utils.py")
    store.upsert_node(_make_symbol("User", kind="class", parent=None), "models.py")
    store.commit()
    results = store.search_nodes("auth", limit=10)
    assert len(results) >= 1
    assert any(r["name"] == "authenticate_user" for r in results)


def test_search_nodes_no_match(store):
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.commit()
    results = store.search_nodes("nonexistent")
    assert results == []


def test_get_all_files(store):
    store.upsert_node(_make_symbol("A", kind="function", parent=None), "a.py")
    store.upsert_node(_make_symbol("B", kind="function", parent=None), "b.py")
    store.commit()
    files = store.get_all_files()
    assert set(files) == {"a.py", "b.py"}


def test_get_stats(store):
    store.upsert_node(_make_symbol("A", kind="function", parent=None), "a.py")
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 5)
    store.commit()
    stats = store.get_stats()
    assert stats["total_nodes"] == 1
    assert stats["total_edges"] == 1
```

- [ ] **Step 9: Implement search_nodes, get_all_files, get_stats**

Add to `GraphStore` class:

```python
    def search_nodes(self, query: str, limit: int = 20) -> list[dict]:
        """Keyword search across node names and docstrings."""
        q = f"%{query.lower()}%"
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE LOWER(name) LIKE ? "
            "OR LOWER(qualified_name) LIKE ? "
            "OR LOWER(docstring) LIKE ? LIMIT ?",
            (q, q, q, limit * 3),  # over-fetch for scoring
        ).fetchall()
        return [dict(r) for r in rows[:limit]]

    def get_all_files(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT file_path FROM nodes ORDER BY file_path"
        ).fetchall()
        return [r["file_path"] for r in rows]

    def get_stats(self) -> dict:
        nodes = self._conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()["c"]
        edges = self._conn.execute("SELECT COUNT(*) as c FROM edges").fetchone()["c"]
        return {"total_nodes": nodes, "total_edges": edges}
```

- [ ] **Step 10: Run all tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: All PASS (23 tests)

- [ ] **Step 11: Write failing test for resolve_bare_call_targets**

Add to `tests/test_graph.py`:

```python
def test_resolve_bare_call_targets(store):
    """Bare target 'save' should resolve to 'models.py::User.save'."""
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("create", kind="function", parent=None), "app.py")
    # Bare call — parser couldn't resolve cross-file
    store.upsert_edge("CALLS", "app.py::create", "save", "app.py", 10)
    # Import edge for disambiguation
    store.upsert_edge("IMPORTS", "app.py", "models.py", "app.py", 1)
    store.commit()

    resolved = store.resolve_bare_call_targets()
    assert resolved >= 1

    edges = store.get_edges_by_source("app.py::create")
    assert edges[0]["target_qualified"] == "models.py::User.save"


def test_resolve_bare_ambiguous_leaves_bare(store):
    """Two symbols named 'save', no import to disambiguate — leave bare."""
    store.upsert_node(_make_symbol("save", parent="User"), "models.py")
    store.upsert_node(_make_symbol("save", parent="Product"), "products.py")
    store.upsert_node(_make_symbol("handler", kind="function", parent=None), "app.py")
    store.upsert_edge("CALLS", "app.py::handler", "save", "app.py", 10)
    store.commit()

    store.resolve_bare_call_targets()

    edges = store.get_edges_by_source("app.py::handler")
    # Should remain bare — ambiguous
    assert edges[0]["target_qualified"] == "save"
```

- [ ] **Step 12: Implement resolve_bare_call_targets**

Add to `GraphStore` class:

```python
    def resolve_bare_call_targets(self) -> int:
        """Resolve bare-name CALLS targets using the global node table."""
        bare_edges = self._conn.execute(
            "SELECT id, source_qualified, target_qualified, file_path "
            "FROM edges WHERE kind = 'CALLS' AND target_qualified NOT LIKE '%::%'"
        ).fetchall()
        if not bare_edges:
            return 0

        # name -> list of qualified_names
        node_lookup: dict[str, list[str]] = {}
        for row in self._conn.execute(
            "SELECT name, qualified_name FROM nodes "
            "WHERE kind IN ('function', 'method', 'class')"
        ).fetchall():
            node_lookup.setdefault(row["name"], []).append(row["qualified_name"])

        # source_file -> set of imported files
        import_targets: dict[str, set[str]] = {}
        for row in self._conn.execute(
            "SELECT DISTINCT file_path, target_qualified FROM edges "
            "WHERE kind = 'IMPORTS'"
        ).fetchall():
            target = row["target_qualified"]
            target_file = target.split("::", 1)[0] if "::" in target else target
            import_targets.setdefault(row["file_path"], set()).add(target_file)

        resolved = 0
        for edge in bare_edges:
            bare_name = edge["target_qualified"]
            candidates = node_lookup.get(bare_name, [])
            if not candidates:
                continue
            if len(candidates) == 1:
                qualified = candidates[0]
            else:
                src_file = edge["file_path"]
                imported_files = import_targets.get(src_file, set())
                imported = [
                    c for c in candidates
                    if c.split("::", 1)[0] in imported_files
                ]
                if len(imported) == 1:
                    qualified = imported[0]
                else:
                    continue
            self._conn.execute(
                "UPDATE edges SET target_qualified = ? WHERE id = ?",
                (qualified, edge["id"]),
            )
            resolved += 1

        if resolved:
            self._conn.commit()
        return resolved
```

- [ ] **Step 13: Run all tests**

Run: `.venv/bin/python -m pytest tests/test_graph.py -v`
Expected: All PASS (25 tests)

- [ ] **Step 14: Lint**

Run: `.venv/bin/ruff check src/ii_structure/graph.py tests/test_graph.py`
Expected: All checks passed

- [ ] **Step 15: Commit**

```bash
git add src/ii_structure/graph.py tests/test_graph.py
git commit -m "feat: GraphStore analysis queries — blast radius, dead code, test coverage, bare call resolution"
```

---

## Task 3: EdgeInfo Dataclass and Python Call Extraction

**Files:**
- Modify: `src/ii_structure/parser.py`
- Create: `tests/test_edge_extraction.py`

- [ ] **Step 1: Write failing tests for Python edge extraction**

```python
# tests/test_edge_extraction.py
"""Tests for call/import/test edge extraction from source code."""
import textwrap
import pytest
from ii_structure.parser import parse_file, EdgeInfo


def test_extracts_function_call():
    source = textwrap.dedent("""\
        def caller():
            helper()

        def helper():
            return 42
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert len(call_edges) >= 1
    targets = {e.target for e in call_edges}
    assert "helper" in targets


def test_extracts_method_call():
    source = textwrap.dedent("""\
        class User:
            def save(self):
                pass

            def process(self):
                self.save()
    """)
    result = parse_file("models.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "save" in targets


def test_extracts_imported_call():
    source = textwrap.dedent("""\
        from utils import validate

        def process(data):
            validate(data)
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "validate" in targets


def test_extracts_import_edges():
    source = textwrap.dedent("""\
        from models import User
        import os
    """)
    result = parse_file("app.py", source)
    import_edges = [e for e in result.edges if e.kind == "IMPORTS"]
    assert len(import_edges) >= 1
    targets = {e.target for e in import_edges}
    assert "models" in targets or "models.User" in targets


def test_extracts_tested_by_edges():
    source = textwrap.dedent("""\
        def test_save():
            user = User()
            user.save()
    """)
    result = parse_file("test_models.py", source)
    # Calls from test functions should be TESTED_BY
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(tested_edges) >= 1


def test_no_edges_from_class_definition():
    """Class definition itself shouldn't generate call edges."""
    source = textwrap.dedent("""\
        class User:
            pass
    """)
    result = parse_file("models.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert len(call_edges) == 0


def test_nested_call_extraction():
    source = textwrap.dedent("""\
        def process():
            result = transform(validate(data))
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "transform" in targets
    assert "validate" in targets


def test_edge_has_line_number():
    source = textwrap.dedent("""\
        def caller():
            helper()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert all(e.line > 0 for e in call_edges)


def test_edge_has_source_qualified():
    source = textwrap.dedent("""\
        def caller():
            helper()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert any("caller" in e.source for e in call_edges)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_edge_extraction.py -v`
Expected: FAIL — `EdgeInfo` not importable, `result.edges` doesn't exist

- [ ] **Step 3: Add EdgeInfo dataclass and extend ParseResult**

In `src/ii_structure/parser.py`, add after the `ImportInfo` dataclass:

```python
@dataclass
class EdgeInfo:
    kind: str       # CALLS, IMPORTS, TESTED_BY
    source: str     # qualified name of caller
    target: str     # qualified name or bare name of callee
    file_path: str
    line: int = 0
```

Modify `ParseResult`:

```python
@dataclass
class ParseResult:
    symbols: list[SymbolInfo]
    imports: list[ImportInfo]
    edges: list[EdgeInfo]
    error: str | None
```

- [ ] **Step 4: Add call extraction to Python parse_file**

Modify `parse_file()` in `src/ii_structure/parser.py`:

```python
def parse_file(file_path: str, source: str) -> ParseResult:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return ParseResult(symbols=[], imports=[], edges=[], error=str(e))

    symbols: list[SymbolInfo] = []
    imports: list[ImportInfo] = []
    edges: list[EdgeInfo] = []

    _extract_symbols(tree, symbols, parent_path=None)
    _extract_imports(tree, imports)
    _extract_edges(tree, file_path, edges)

    return ParseResult(symbols=symbols, imports=imports, edges=edges, error=None)
```

Add edge extraction functions:

```python
def _is_test_file_path(file_path: str) -> bool:
    """Check if file path looks like a test file."""
    name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    return name.startswith("test_") or name.endswith("_test.py")


def _extract_edges(tree: ast.Module, file_path: str, edges: list[EdgeInfo]) -> None:
    """Extract CALLS, IMPORTS, and TESTED_BY edges from the AST."""
    is_test = _is_test_file_path(file_path)

    # IMPORTS edges from import statements
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(EdgeInfo(
                    kind="IMPORTS", source=file_path,
                    target=alias.name, file_path=file_path, line=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                edges.append(EdgeInfo(
                    kind="IMPORTS", source=file_path,
                    target=node.module, file_path=file_path, line=node.lineno,
                ))

    # Walk functions/methods for CALLS edges
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _extract_calls_from_function(node, file_path, edges, is_test)


def _extract_calls_from_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: str,
    edges: list[EdgeInfo],
    is_test_file: bool,
) -> None:
    """Extract CALLS (or TESTED_BY) edges from a function body."""
    # Determine the qualified source name
    parent = getattr(func_node, "_ii_parent", None)
    if parent:
        source_qn = f"{file_path}::{parent}.{func_node.name}"
    else:
        source_qn = f"{file_path}::{func_node.name}"

    is_test_func = func_node.name.startswith("test_")
    edge_kind = "TESTED_BY" if (is_test_file and is_test_func) else "CALLS"

    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name:
                edges.append(EdgeInfo(
                    kind=edge_kind,
                    source=source_qn,
                    target=call_name,
                    file_path=file_path,
                    line=node.lineno,
                ))


def _get_call_name(node: ast.Call) -> str | None:
    """Extract the function/method name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None
```

Also need to tag function nodes with their parent class. Modify `_extract_symbols` to set `_ii_parent`:

In the section where we process `ast.FunctionDef` inside a class, add:
```python
node._ii_parent = parent_path  # tag for edge extraction
```

- [ ] **Step 5: Fix all places that construct ParseResult to include edges=[]**

Search for `ParseResult(` in all backend files and add `edges=[]`:
- `src/ii_structure/backends/golang.py` — GoBackend.parse_file return
- `src/ii_structure/backends/typescript.py` — TypeScriptBackend.parse_file return
- Any test fixtures that construct ParseResult

- [ ] **Step 6: Run edge extraction tests**

Run: `.venv/bin/python -m pytest tests/test_edge_extraction.py -v`
Expected: All PASS

- [ ] **Step 7: Run full existing test suite to check for regressions**

Run: `.venv/bin/python -m pytest -v`
Expected: All 241 existing tests PASS (ParseResult change is backward compatible)

- [ ] **Step 8: Lint**

Run: `.venv/bin/ruff check src/ii_structure/parser.py tests/test_edge_extraction.py`

- [ ] **Step 9: Commit**

```bash
git add src/ii_structure/parser.py src/ii_structure/backends/golang.py \
  src/ii_structure/backends/typescript.py tests/test_edge_extraction.py
git commit -m "feat: EdgeInfo dataclass and Python call extraction from AST"
```

---

## Task 4: Go and TypeScript Edge Extraction

**Files:**
- Modify: `src/ii_structure/backends/golang.py`
- Modify: `src/ii_structure/backends/typescript.py`
- Modify: `tests/test_edge_extraction.py`

- [ ] **Step 1: Write failing tests for Go edge extraction**

Add to `tests/test_edge_extraction.py`:

```python
from ii_structure.backends.golang import GoBackend


def test_go_extracts_function_call():
    source = """\
package main

func caller() {
    helper()
}

func helper() int {
    return 42
}
"""
    backend = GoBackend()
    result = backend.parse_file("main.go", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "helper" in targets


def test_go_extracts_method_call():
    source = """\
package main

type Server struct{}

func (s *Server) Start() {
    s.Init()
}

func (s *Server) Init() {}
"""
    backend = GoBackend()
    result = backend.parse_file("server.go", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "Init" in targets
```

- [ ] **Step 2: Write failing tests for TypeScript edge extraction**

Add to `tests/test_edge_extraction.py`:

```python
from ii_structure.backends.typescript import TypeScriptBackend


def test_ts_extracts_function_call():
    source = """\
function caller(): void {
    helper();
}

function helper(): number {
    return 42;
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "helper" in targets


def test_ts_extracts_new_expression():
    source = """\
class User {}

function createUser(): User {
    return new User();
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "User" in targets


def test_ts_extracts_method_call():
    source = """\
class Service {
    save(): void {
        this.validate();
    }
    validate(): boolean {
        return true;
    }
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("service.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "validate" in targets
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_edge_extraction.py -k "go_ or ts_" -v`
Expected: FAIL

- [ ] **Step 4: Add call extraction to GoBackend.parse_file**

In `src/ii_structure/backends/golang.py`, modify `parse_file` to also walk `call_expression` nodes and emit `EdgeInfo` objects. Use tree-sitter's `call_expression` node type. The pattern:

```python
# Inside the AST walk, when encountering call_expression nodes:
from ii_structure.parser import EdgeInfo

# In the extraction loop, add:
if child.type == "call_expression":
    call_name = _get_text(child.children[0], source) if child.children else None
    if call_name and "." in call_name:
        call_name = call_name.rsplit(".", 1)[-1]
    if call_name:
        edges.append(EdgeInfo(
            kind="CALLS",
            source=enclosing_func_qn,
            target=call_name,
            file_path=file_path,
            line=child.start_point[0] + 1,
        ))
```

Add `edges` list to the parse_file method and include it in the returned `ParseResult`.

- [ ] **Step 5: Add call extraction to TypeScriptBackend.parse_file**

Same pattern as Go but with `call_expression` and `new_expression` node types.

- [ ] **Step 6: Run all edge extraction tests**

Run: `.venv/bin/python -m pytest tests/test_edge_extraction.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: All existing tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/ii_structure/backends/golang.py src/ii_structure/backends/typescript.py \
  tests/test_edge_extraction.py
git commit -m "feat: Go and TypeScript call extraction via tree-sitter"
```

---

## Task 5: Migrate Index from JSON to SQLite

**Files:**
- Rewrite: `src/ii_structure/index.py`
- Modify: `tests/test_index.py` (update tests for new backend)

- [ ] **Step 1: Read the existing Index tests to understand expected behavior**

Run: `ii-structure body Index 2>&1` and `ii-structure outline tests/test_index.py --depth full 2>&1`

The public API that must be preserved:
- `Index.build(root)` → `Index`
- `Index.load(state_dir)` → `Index`
- `Index.save(state_dir)`
- `Index.refresh(root)`
- `Index.search_symbols(name_path)` → `list[dict]`
- `Index.get_symbols(rel_path)` → `list[dict]`
- `Index.all_symbols()` → `list[dict]`
- `Index.files` dict access (used by commands)

- [ ] **Step 2: Rewrite Index class to wrap GraphStore**

Rewrite `src/ii_structure/index.py` so that:
- `Index.__init__` opens a `GraphStore`
- `Index.build` parses all files, stores nodes + edges in SQLite
- `Index.load` opens existing graph.db
- `Index.refresh` detects changed files, re-parses + updates edges
- `Index.search_symbols` queries nodes table with the existing name_path logic
- `Index.get_symbols` queries by file_path
- `Index.all_symbols` returns all nodes
- `Index.files` property returns a dict-like view for backward compatibility
- Auto-migration: if `index.json` exists and `graph.db` doesn't, rebuild from scratch and delete JSON

Key: the `files` dict property needs to return data shaped like the old JSON entries so existing commands work during the transition. Each entry needs `symbols`, `imports`, `mtime`, `content_hash`, `parse_error`.

- [ ] **Step 3: Update existing index tests**

Modify `tests/test_index.py` to work with SQLite backend. Key changes:
- `save` now writes to `graph.db` not `index.json`
- `load` reads from `graph.db`
- Internal storage is SQLite but public API is identical

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: All tests PASS. This is the critical regression checkpoint.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/index.py tests/test_index.py
git commit -m "feat: migrate Index from JSON to SQLite GraphStore"
```

---

## Task 6: Rewrite usages and imports commands

**Files:**
- Rewrite: `src/ii_structure/commands/usages.py`
- Rewrite: `src/ii_structure/commands/imports.py`
- Modify: `src/ii_structure/resolver.py` (remove dead code)
- Modify: `src/ii_structure/backends/base.py` (remove find_usages from Protocol)

- [ ] **Step 1: Rewrite usages.py to use edge queries**

Replace the entire `execute()` function. Instead of dispatching to backends:

```python
def execute(idx, project_root, name, path_scope=None, kind_filter=None,
            limit=50, include_tests=True):
    candidates = idx.search_symbols(name)
    if not candidates:
        return []

    # Build qualified name from first candidate
    candidate = candidates[0]
    file_path = candidate["file"]
    parent = candidate.get("parent")
    qn = f"{file_path}::{parent}.{candidate['name']}" if parent else f"{file_path}::{candidate['name']}"

    # Query edges
    edges = idx.graph.get_edges_by_target(qn)

    results = []
    for edge in edges:
        if edge["kind"] != "CALLS":
            continue
        source_node = idx.graph.get_node(edge["source_qualified"])
        if not source_node:
            continue
        # Apply filters
        if path_scope and not source_node["file_path"].startswith(path_scope):
            continue
        if not include_tests and _is_test_file(source_node["file_path"]):
            continue
        results.append({
            "file": source_node["file_path"],
            "line": edge["line"],
            "kind": "reference",
            "context": source_node.get("signature", ""),
        })

    if kind_filter:
        results = [r for r in results if r["kind"] == kind_filter]

    return results[:limit]
```

- [ ] **Step 2: Rewrite imports.py to use edge queries**

Replace the entire file. Remove all 7 helper functions. The new `execute()`:

```python
def execute(idx, file, depth=1, include_external=False):
    # Forward imports
    import_edges = idx.graph.get_edges_by_source(file)  # file-level edges
    imports = []
    for edge in import_edges:
        if edge["kind"] != "IMPORTS":
            continue
        imports.append({
            "module": edge["target_qualified"],
            "file": edge["target_qualified"],
            "line": edge["line"],
        })

    # Reverse imports (who imports this file?)
    reverse_edges = idx.graph.get_edges_by_target(file)
    imported_by = []
    for edge in reverse_edges:
        if edge["kind"] != "IMPORTS":
            continue
        imported_by.append({
            "file": edge["source_qualified"],
            "module": edge["source_qualified"],
        })

    return {"file": file, "imports": imports, "imported_by": imported_by}
```

- [ ] **Step 3: Remove dead code from resolver.py**

Remove: `find_usages()`, `_classify_reference()`, `_find_name_column()`, `_get_context_line()`.
Keep: `get_definition_source()`, `_read_symbol_source()`, `_is_test_file()`.

- [ ] **Step 4: Remove find_usages from LanguageBackend Protocol**

In `src/ii_structure/backends/base.py`, remove the `find_usages` method from the Protocol. Keep `parse_file` and `get_definition_source`.

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -v`
Expected: Usages and imports tests may need updating to match new output shapes. Fix any failures.

- [ ] **Step 6: Commit**

```bash
git add src/ii_structure/commands/usages.py src/ii_structure/commands/imports.py \
  src/ii_structure/resolver.py src/ii_structure/backends/base.py
git commit -m "feat: rewrite usages/imports as edge queries, remove dead code from resolver"
```

---

## Task 7: New Commands — blast-radius, dead-code, test-coverage

**Files:**
- Create: `src/ii_structure/commands/blast_radius.py`
- Create: `src/ii_structure/commands/dead_code.py`
- Create: `src/ii_structure/commands/test_coverage.py`
- Create: `tests/test_commands/test_blast_radius.py`
- Create: `tests/test_commands/test_dead_code.py`
- Create: `tests/test_commands/test_test_coverage.py`
- Modify: `src/ii_structure/cli.py`

- [ ] **Step 1: Write blast_radius command + tests**

```python
# src/ii_structure/commands/blast_radius.py
def execute(idx, project_root, name, max_depth=3, file_hint=None):
    candidates = idx.search_symbols(name)
    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]
    if not candidates:
        raise ValueError(f"Symbol '{name}' not found in index")

    candidate = candidates[0]
    file_path = candidate["file"]
    parent = candidate.get("parent")
    qn = f"{file_path}::{parent}.{candidate['name']}" if parent else f"{file_path}::{candidate['name']}"

    result = idx.graph.get_impact_radius(qn, max_depth=max_depth)

    affected = []
    for node in result["impacted_nodes"]:
        affected.append({
            "symbol": node["name"],
            "file": node["file_path"],
            "line": node.get("line_start"),
            "depth": node.get("depth", 0),
            "kind": node["kind"],
        })

    # Get test info
    tests = idx.graph.get_transitive_tests(qn)
    test_names = [t["name"] for t in tests]

    return {
        "symbol": name,
        "file": file_path,
        "affected": affected,
        "affected_files": result["impacted_files"],
        "tests": test_names,
        "total": result["total_impacted"],
    }
```

- [ ] **Step 2: Write dead_code command + tests**

```python
# src/ii_structure/commands/dead_code.py
def execute(idx, file_hint=None):
    dead = idx.graph.get_dead_symbols(file_path=file_hint)
    return [{
        "symbol": d["name"],
        "file": d["file_path"],
        "line": d.get("line_start"),
        "kind": d["kind"],
        "parent": d.get("parent_name"),
    } for d in dead]
```

- [ ] **Step 3: Write test_coverage command + tests**

```python
# src/ii_structure/commands/test_coverage.py
def execute(idx, project_root, name, max_depth=2, file_hint=None):
    candidates = idx.search_symbols(name)
    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]
    if not candidates:
        raise ValueError(f"Symbol '{name}' not found in index")

    candidate = candidates[0]
    file_path = candidate["file"]
    parent = candidate.get("parent")
    qn = f"{file_path}::{parent}.{candidate['name']}" if parent else f"{file_path}::{candidate['name']}"

    tests = idx.graph.get_transitive_tests(qn, max_depth=max_depth)

    return {
        "symbol": name,
        "file": file_path,
        "tests": [{
            "name": t["name"],
            "file": t["file_path"],
            "indirect": t.get("indirect", False),
        } for t in tests],
        "total_tests": len(tests),
        "covered": len(tests) > 0,
    }
```

- [ ] **Step 4: Add Click commands to cli.py**

Add `blast-radius`, `dead-code`, `test-coverage` commands following the existing pattern.

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/python -m pytest -v`

- [ ] **Step 6: Commit**

```bash
git add src/ii_structure/commands/blast_radius.py src/ii_structure/commands/dead_code.py \
  src/ii_structure/commands/test_coverage.py src/ii_structure/cli.py \
  tests/test_commands/test_blast_radius.py tests/test_commands/test_dead_code.py \
  tests/test_commands/test_test_coverage.py
git commit -m "feat: add blast-radius, dead-code, test-coverage commands"
```

---

## Task 8: Update Write Commands to Refresh Edges

**Files:**
- Modify: `src/ii_structure/commands/replace_body.py`
- Modify: `src/ii_structure/commands/insert_symbol.py`

- [ ] **Step 1: Update replace_body to refresh edges after write**

After writing the file, instead of just `_parse_and_build_entry`, call the new Index method that re-parses and updates nodes + edges in SQLite. Also re-parse dependent files if the symbol signature changed.

- [ ] **Step 2: Update insert_symbol similarly**

Same pattern.

- [ ] **Step 3: Run all tests including write edge case tests**

Run: `.venv/bin/python -m pytest tests/test_commands/test_replace_body.py tests/test_commands/test_insert_symbol.py tests/test_commands/test_write_edge_cases.py tests/test_commands/test_content_hash.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/ii_structure/commands/replace_body.py src/ii_structure/commands/insert_symbol.py
git commit -m "feat: write commands refresh edges after edits"
```

---

## Task 9: Update help_content.yaml, CLAUDE_MD_SECTION, and README

**Files:**
- Modify: `src/ii_structure/help_content.yaml`
- Modify: `src/ii_structure/cli.py` (CLAUDE_MD_SECTION)
- Rewrite: `README.md`

- [ ] **Step 1: Add help entries for blast-radius, dead-code, test-coverage**

- [ ] **Step 2: Update CLAUDE_MD_SECTION with new commands in the decision tree**

- [ ] **Step 3: Rewrite README.md**

Complete rewrite reflecting:
- Graph-backed architecture
- 12 commands (7 read, 2 write, 3 analysis)
- Updated token savings
- Safe write workflow with edge refresh
- SQLite storage explanation

- [ ] **Step 4: Commit**

```bash
git add src/ii_structure/help_content.yaml src/ii_structure/cli.py README.md
git commit -m "docs: update help, CLAUDE.md, and README for graph persistence"
```

---

## Task 10: Final Verification and Cleanup

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Lint entire codebase**

Run: `.venv/bin/ruff check src/ tests/`

- [ ] **Step 3: Test all commands manually on ii-structure's own codebase**

```bash
ii-structure files --summary --path src/
ii-structure outline src/ii_structure/graph.py --depth full
ii-structure locate GraphStore
ii-structure body GraphStore/get_impact_radius
ii-structure search blast
ii-structure usages Index
ii-structure imports src/ii_structure/graph.py
ii-structure blast-radius Index/search_symbols
ii-structure dead-code --file src/ii_structure/resolver.py
ii-structure test-coverage Index/build
echo 'def helper(): return 99' | ii-structure replace-body helper
echo 'def new_func(): pass' | ii-structure insert-symbol --after helper
```

- [ ] **Step 4: Verify index.json is no longer created**

```bash
ls .ii-structure/
# Should show graph.db, NOT index.json
```

- [ ] **Step 5: Run benchmarks on user-provided codebases**

- [ ] **Step 6: Final commit and push**

```bash
git push origin feature/graph-persistence
```
