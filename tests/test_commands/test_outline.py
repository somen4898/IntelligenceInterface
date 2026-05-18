import pytest
from ii_structure.index import Index
from ii_structure.commands.outline import execute


def test_outline_returns_all_symbols(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py")
    symbols = result["symbols"]
    names = {s["name"] for s in symbols}
    assert "User" in names
    assert "Product" in names
    assert "MAX_USERS" in names


def test_outline_top_depth(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py", depth="top")
    symbols = result["symbols"]
    # top-level only: User, Product, MAX_USERS — no methods
    assert all(s.get("parent") is None for s in symbols)


def test_outline_full_depth(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py", depth="full")
    symbols = result["symbols"]
    names = {s["name"] for s in symbols}
    assert "save" in names
    assert "delete" in names


def test_outline_kind_filter(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py", kind="class")
    symbols = result["symbols"]
    assert all(s["kind"] == "class" for s in symbols)
    assert len(symbols) == 2


def test_outline_includes_imports(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="views.py")
    assert "imports" in result
    modules = {i["module"] for i in result["imports"]}
    assert "models" in modules


def test_outline_file_not_found(simple_project):
    idx = Index.build(simple_project)
    with pytest.raises(FileNotFoundError):
        execute(idx, file="nonexistent.py")


def test_outline_includes_file_path(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py")
    assert result["file"] == "models.py"
