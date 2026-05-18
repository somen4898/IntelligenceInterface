from ii_structure.index import Index
from ii_structure.commands.search import execute


def test_search_exact_name(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="User")
    assert len(results) >= 1
    assert results[0]["name"] == "User"


def test_search_prefix(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="load")
    assert any(r["name"] == "load_config" for r in results)


def test_search_substring(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="config")
    names = {r["name"] for r in results}
    assert "load_config" in names or "ConfigManager" in names


def test_search_docstring(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="persist")
    # "Persist the user" is in User.save's docstring
    assert len(results) >= 1


def test_search_ranking(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="User")
    # Exact match should be first
    assert results[0]["name"] == "User"


def test_search_limit(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="s", limit=3)
    assert len(results) <= 3


def test_search_no_match(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="zzzznotfound")
    assert results == []


def test_search_result_shape(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, query="User")
    r = results[0]
    assert "file" in r
    assert "name" in r
    assert "kind" in r
    assert "line" in r
    assert "signature" in r
