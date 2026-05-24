"""Tests for ii_structure.graph — GraphStore SQLite-backed knowledge graph."""
import os

import pytest

from ii_structure.graph import GraphStore, _sanitize_name
from ii_structure.parser import SymbolInfo


@pytest.fixture
def tmp_db(tmp_path):
    """Yield a temporary DB path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def store(tmp_db):
    """Yield an open GraphStore, close after test."""
    gs = GraphStore(tmp_db)
    yield gs
    gs.close()


def _make_symbol(
    name="foo",
    kind="function",
    line=1,
    end_line=5,
    signature="def foo():",
    docstring=None,
    parent=None,
    children=None,
    decorators=None,
):
    return SymbolInfo(
        name=name,
        kind=kind,
        line=line,
        end_line=end_line,
        signature=signature,
        docstring=docstring,
        parent=parent,
        children=children or [],
        decorators=decorators or [],
    )


# --- 1. test_creates_db_file ---
def test_creates_db_file(tmp_db):
    gs = GraphStore(tmp_db)
    try:
        assert os.path.exists(tmp_db)
    finally:
        gs.close()


# --- 2. test_schema_has_tables ---
def test_schema_has_tables(store):
    cur = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = sorted(row[0] for row in cur.fetchall())
    assert "edges" in tables
    assert "metadata" in tables
    assert "nodes" in tables


# --- 3. test_wal_mode_enabled ---
def test_wal_mode_enabled(store):
    cur = store._conn.execute("PRAGMA journal_mode")
    mode = cur.fetchone()[0]
    assert mode.lower() == "wal"


# --- 4. test_schema_version_set ---
def test_schema_version_set(store):
    cur = store._conn.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    )
    row = cur.fetchone()
    assert row is not None
    assert int(row[0]) >= 1


# --- 5. test_upsert_node ---
def test_upsert_node(store):
    sym = _make_symbol(name="bar", kind="function")
    nid = store.upsert_node(sym, "src/app.py", "abc123")
    assert nid is not None
    assert nid > 0


# --- 6. test_get_node ---
def test_get_node(store):
    sym = _make_symbol(name="bar", kind="function")
    store.upsert_node(sym, "src/app.py", "abc123")
    qn = store._make_qualified("bar", "src/app.py", None)
    node = store.get_node(qn)
    assert node is not None
    assert node["name"] == "bar"
    assert node["kind"] == "function"
    assert node["file_path"] == "src/app.py"
    assert node["file_hash"] == "abc123"


# --- 7. test_get_node_not_found ---
def test_get_node_not_found(store):
    assert store.get_node("nonexistent::thing") is None


# --- 8. test_get_nodes_by_file ---
def test_get_nodes_by_file(store):
    store.upsert_node(_make_symbol(name="a"), "file1.py", "h1")
    store.upsert_node(_make_symbol(name="b"), "file1.py", "h1")
    store.upsert_node(_make_symbol(name="c"), "file2.py", "h2")

    nodes = store.get_nodes_by_file("file1.py")
    assert len(nodes) == 2
    names = {n["name"] for n in nodes}
    assert names == {"a", "b"}


# --- 9. test_upsert_node_updates_existing ---
def test_upsert_node_updates_existing(store):
    sym1 = _make_symbol(name="x", kind="function", signature="def x():")
    store.upsert_node(sym1, "f.py", "h1")

    sym2 = _make_symbol(name="x", kind="function", signature="def x(a, b):")
    store.upsert_node(sym2, "f.py", "h2")

    qn = store._make_qualified("x", "f.py", None)
    node = store.get_node(qn)
    assert node["signature"] == "def x(a, b):"
    assert node["file_hash"] == "h2"


# --- 10. test_remove_file_data ---
def test_remove_file_data(store):
    store.upsert_node(_make_symbol(name="a"), "f.py", "h1")
    store.upsert_edge("calls", "f.py::a", "f.py::b", "f.py", 10)

    store.remove_file_data("f.py")

    assert store.get_nodes_by_file("f.py") == []
    assert store.get_edges_by_source("f.py::a") == []


# --- 11. test_upsert_edge ---
def test_upsert_edge(store):
    eid = store.upsert_edge("calls", "a::foo", "b::bar", "a.py", 10)
    assert eid is not None
    assert eid > 0


# --- 12. test_get_edges_by_target ---
def test_get_edges_by_target(store):
    store.upsert_edge("calls", "a::foo", "b::bar", "a.py", 10)
    store.upsert_edge("imports", "c::baz", "b::bar", "c.py", 5)

    edges = store.get_edges_by_target("b::bar")
    assert len(edges) == 2
    kinds = {e["kind"] for e in edges}
    assert kinds == {"calls", "imports"}


# --- 13. test_get_edges_by_source ---
def test_get_edges_by_source(store):
    store.upsert_edge("calls", "a::foo", "b::bar", "a.py", 10)
    store.upsert_edge("calls", "a::foo", "c::baz", "a.py", 20)

    edges = store.get_edges_by_source("a::foo")
    assert len(edges) == 2


# --- 14. test_remove_file_data_removes_edges ---
def test_remove_file_data_removes_edges(store):
    store.upsert_edge("calls", "a::foo", "b::bar", "a.py", 10)
    store.upsert_edge("calls", "a::foo", "c::baz", "a.py", 20)
    store.upsert_edge("imports", "x::y", "z::w", "other.py", 1)

    store.remove_file_data("a.py")

    assert store.get_edges_by_source("a::foo") == []
    # edges from other file unaffected
    assert len(store.get_edges_by_source("x::y")) == 1


# --- 15. test_store_file_nodes_edges_atomic ---
def test_store_file_nodes_edges_atomic(store):
    # Insert initial data
    store.upsert_node(_make_symbol(name="old_fn"), "f.py", "h1")
    store.upsert_edge("calls", "f.py::old_fn", "x::y", "f.py", 1)

    # Replace with new data atomically
    new_symbols = [
        _make_symbol(name="new_fn", kind="function", line=10, end_line=20),
    ]
    new_edges = [
        ("imports", "f.py::new_fn", "z::w", "f.py", 5),
    ]
    store.store_file_nodes_edges("f.py", new_symbols, new_edges, "h2")

    # Old data should be gone
    assert store.get_node("f.py::old_fn") is None
    assert store.get_edges_by_source("f.py::old_fn") == []

    # New data should be present
    node = store.get_node("f.py::new_fn")
    assert node is not None
    assert node["name"] == "new_fn"

    edges = store.get_edges_by_source("f.py::new_fn")
    assert len(edges) == 1
    assert edges[0]["kind"] == "imports"


# --- 16. test_get_all_files ---
def test_get_all_files(store):
    store.upsert_node(_make_symbol(name="a"), "file1.py", "h1")
    store.upsert_node(_make_symbol(name="b"), "file2.py", "h2")
    store.upsert_node(_make_symbol(name="c"), "file1.py", "h1")

    files = store.get_all_files()
    assert sorted(files) == ["file1.py", "file2.py"]


# --- 17. test_get_stats ---
def test_get_stats(store):
    store.upsert_node(_make_symbol(name="a"), "f.py", "h1")
    store.upsert_node(_make_symbol(name="b"), "f.py", "h1")
    store.upsert_edge("calls", "f.py::a", "f.py::b", "f.py", 5)

    stats = store.get_stats()
    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1


# --- 18. test_context_manager ---
def test_context_manager(tmp_db):
    with GraphStore(tmp_db) as gs:
        gs.upsert_node(_make_symbol(name="x"), "f.py", "h")
        node = gs.get_node("f.py::x")
        assert node is not None

    # DB file should still exist after closing
    assert os.path.exists(tmp_db)

    # Re-open and verify data persisted
    with GraphStore(tmp_db) as gs2:
        node = gs2.get_node("f.py::x")
        assert node is not None
        assert node["name"] == "x"


# --- _sanitize_name tests ---
def test_sanitize_name_strips_control_chars():
    assert _sanitize_name("hello\x00world") == "helloworld"
    assert _sanitize_name("foo\x01bar\x1f") == "foobar"


def test_sanitize_name_keeps_tab_newline():
    assert _sanitize_name("hello\tworld") == "hello\tworld"
    assert _sanitize_name("hello\nworld") == "hello\nworld"


def test_sanitize_name_caps_length():
    long = "a" * 300
    assert len(_sanitize_name(long)) == 256


# ============================================================
# Analysis query tests
# ============================================================


# --- Blast radius tests ---


def test_blast_radius_direct(store):
    """A→B→C chain, blast from C depth 1 finds B."""
    store.upsert_node(_make_symbol(name="A"), "a.py", "h")
    store.upsert_node(_make_symbol(name="B"), "b.py", "h")
    store.upsert_node(_make_symbol(name="C"), "c.py", "h")
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 1)
    store.upsert_edge("CALLS", "b.py::B", "c.py::C", "b.py", 2)

    result = store.get_impact_radius("c.py::C", max_depth=1)
    qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "b.py::B" in qns
    assert "a.py::A" not in qns


def test_blast_radius_transitive(store):
    """A→B→C chain, depth 3 finds both A and B."""
    store.upsert_node(_make_symbol(name="A"), "a.py", "h")
    store.upsert_node(_make_symbol(name="B"), "b.py", "h")
    store.upsert_node(_make_symbol(name="C"), "c.py", "h")
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 1)
    store.upsert_edge("CALLS", "b.py::B", "c.py::C", "b.py", 2)

    result = store.get_impact_radius("c.py::C", max_depth=3)
    qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "a.py::A" in qns
    assert "b.py::B" in qns


def test_blast_radius_depth_limit(store):
    """Depth 1 from C finds B but NOT A."""
    store.upsert_node(_make_symbol(name="A"), "a.py", "h")
    store.upsert_node(_make_symbol(name="B"), "b.py", "h")
    store.upsert_node(_make_symbol(name="C"), "c.py", "h")
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 1)
    store.upsert_edge("CALLS", "b.py::B", "c.py::C", "b.py", 2)

    result = store.get_impact_radius("c.py::C", max_depth=1)
    qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "b.py::B" in qns
    assert "a.py::A" not in qns


def test_blast_radius_diamond(store):
    """A→C, B→C. Blast from C finds both A and B."""
    store.upsert_node(_make_symbol(name="A"), "a.py", "h")
    store.upsert_node(_make_symbol(name="B"), "b.py", "h")
    store.upsert_node(_make_symbol(name="C"), "c.py", "h")
    store.upsert_edge("CALLS", "a.py::A", "c.py::C", "a.py", 1)
    store.upsert_edge("CALLS", "b.py::B", "c.py::C", "b.py", 2)

    result = store.get_impact_radius("c.py::C", max_depth=1)
    qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "a.py::A" in qns
    assert "b.py::B" in qns


def test_blast_radius_cycle(store):
    """A→B→A circular, should not infinite loop."""
    store.upsert_node(_make_symbol(name="A"), "a.py", "h")
    store.upsert_node(_make_symbol(name="B"), "b.py", "h")
    store.upsert_edge("CALLS", "a.py::A", "b.py::B", "a.py", 1)
    store.upsert_edge("CALLS", "b.py::B", "a.py::A", "b.py", 2)

    result = store.get_impact_radius("a.py::A", max_depth=3)
    qns = {n["qualified_name"] for n in result["impacted_nodes"]}
    assert "b.py::B" in qns


def test_blast_radius_empty(store):
    """Lonely node with no edges, returns empty."""
    store.upsert_node(_make_symbol(name="lonely"), "l.py", "h")

    result = store.get_impact_radius("l.py::lonely")
    assert result["impacted_nodes"] == []
    assert result["impacted_files"] == []
    assert result["total_impacted"] == 0


# --- Dead code tests ---


def test_get_dead_symbols(store):
    """used_func has no callers → dead. dead_func IS called → not dead."""
    store.upsert_node(_make_symbol(name="used_func"), "app.py", "h")
    store.upsert_node(_make_symbol(name="dead_func"), "app.py", "h")
    # used_func calls dead_func, so dead_func has a caller
    store.upsert_edge("CALLS", "app.py::used_func", "app.py::dead_func", "app.py", 1)

    dead = store.get_dead_symbols()
    dead_names = {d["name"] for d in dead}
    assert "used_func" in dead_names
    assert "dead_func" not in dead_names


def test_dead_code_excludes_tests(store):
    """test_something function not reported as dead."""
    store.upsert_node(
        _make_symbol(name="test_something"), "test_app.py", "h"
    )
    dead = store.get_dead_symbols()
    dead_names = {d["name"] for d in dead}
    assert "test_something" not in dead_names


def test_dead_code_excludes_init_main(store):
    """__init__ and main excluded."""
    store.upsert_node(_make_symbol(name="__init__", kind="method"), "app.py", "h")
    store.upsert_node(_make_symbol(name="main"), "app.py", "h")
    dead = store.get_dead_symbols()
    dead_names = {d["name"] for d in dead}
    assert "__init__" not in dead_names
    assert "main" not in dead_names


def test_dead_code_excludes_dunder(store):
    store.upsert_node(_make_symbol("__str__", kind="method", parent="User"), "models.py", "h")
    store.commit()
    dead = store.get_dead_symbols()
    assert not any(d["name"] == "__str__" for d in dead)


def test_dead_code_excludes_decorated(store):
    sym = _make_symbol("route_handler", kind="function", parent=None)
    sym = SymbolInfo(
        name=sym.name, kind=sym.kind, line=sym.line, end_line=sym.end_line,
        signature=sym.signature, docstring=sym.docstring, parent=sym.parent,
        children=sym.children, decorators=["app.route"],
    )
    store.upsert_node(sym, "app.py", "h")
    store.commit()
    dead = store.get_dead_symbols()
    assert not any(d["name"] == "route_handler" for d in dead)


def test_dead_code_excludes_handle_prefix(store):
    store.upsert_node(_make_symbol("handle_request", kind="function", parent=None), "server.py", "h")
    store.commit()
    dead = store.get_dead_symbols()
    assert not any(d["name"] == "handle_request" for d in dead)


def test_dead_code_excludes_conftest(store):
    store.upsert_node(_make_symbol("my_fixture", kind="function", parent=None), "conftest.py", "h")
    store.commit()
    dead = store.get_dead_symbols()
    assert not any(d["name"] == "my_fixture" for d in dead)


# --- Test coverage tests ---


def test_get_transitive_tests_direct(store):
    """test_save TESTED_BY save → found as direct."""
    store.upsert_node(_make_symbol(name="save"), "models.py", "h")
    store.upsert_node(
        _make_symbol(name="test_save"), "test_models.py", "h"
    )
    store.upsert_edge(
        "TESTED_BY", "test_models.py::test_save", "models.py::save",
        "test_models.py", 1,
    )

    tests = store.get_transitive_tests("models.py::save")
    assert len(tests) == 1
    assert tests[0]["name"] == "test_save"
    assert tests[0]["indirect"] is False


def test_get_transitive_tests_indirect(store):
    """test_create tests create, create calls save → save indirectly tested."""
    store.upsert_node(_make_symbol(name="save"), "models.py", "h")
    store.upsert_node(_make_symbol(name="create"), "models.py", "h")
    store.upsert_node(
        _make_symbol(name="test_create"), "test_models.py", "h"
    )
    # create calls save
    store.upsert_edge(
        "CALLS", "models.py::create", "models.py::save", "models.py", 1
    )
    # test_create TESTED_BY create
    store.upsert_edge(
        "TESTED_BY", "test_models.py::test_create", "models.py::create",
        "test_models.py", 1,
    )

    tests = store.get_transitive_tests("models.py::save")
    assert len(tests) == 1
    assert tests[0]["name"] == "test_create"
    assert tests[0]["indirect"] is True


# --- Search tests ---


def test_search_nodes(store):
    """Finds authenticate_user when searching 'auth'."""
    store.upsert_node(
        _make_symbol(name="authenticate_user", signature="def authenticate_user():"),
        "auth.py", "h",
    )
    store.upsert_node(_make_symbol(name="save"), "models.py", "h")

    results = store.search_nodes("auth")
    names = {r["name"] for r in results}
    assert "authenticate_user" in names
    assert "save" not in names


def test_search_nodes_no_match(store):
    """Returns empty list."""
    store.upsert_node(_make_symbol(name="foo"), "f.py", "h")
    results = store.search_nodes("zzz_nonexistent")
    assert results == []


# --- Bare call resolution tests ---


def test_resolve_bare_call_targets(store):
    """Bare 'save' resolves to 'models.py::User.save' via import."""
    store.upsert_node(
        _make_symbol(name="save", kind="method", parent="User"),
        "models.py", "h",
    )
    store.upsert_node(_make_symbol(name="handler"), "views.py", "h")
    # views.py imports models.py
    store.upsert_edge("IMPORTS", "views.py::handler", "models.py::User", "views.py", 1)
    # bare CALLS edge (no '::')
    store.upsert_edge("CALLS", "views.py::handler", "save", "views.py", 10)

    resolved = store.resolve_bare_call_targets()
    assert resolved >= 1

    # The edge should now point to the qualified name
    edges = store.get_edges_by_source("views.py::handler")
    call_edges = [e for e in edges if e["kind"] == "CALLS"]
    targets = {e["target_qualified"] for e in call_edges}
    assert "models.py::User.save" in targets


def test_resolve_bare_ambiguous_leaves_bare(store):
    """Two candidates, no import to disambiguate → stays bare."""
    store.upsert_node(
        _make_symbol(name="save", kind="method", parent="User"),
        "models.py", "h",
    )
    store.upsert_node(
        _make_symbol(name="save", kind="method", parent="Order"),
        "orders.py", "h",
    )
    store.upsert_node(_make_symbol(name="handler"), "views.py", "h")
    # No IMPORTS edge from views.py to either file
    store.upsert_edge("CALLS", "views.py::handler", "save", "views.py", 10)

    resolved = store.resolve_bare_call_targets()
    assert resolved == 0

    edges = store.get_edges_by_source("views.py::handler")
    call_edges = [e for e in edges if e["kind"] == "CALLS"]
    # Should still be bare
    assert any(e["target_qualified"] == "save" for e in call_edges)


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
