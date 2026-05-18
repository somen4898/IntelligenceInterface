import pytest
from ii_structure.index import Index
from ii_structure.commands.imports import execute


def test_imports_basic(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="views.py")
    assert result["file"] == "views.py"
    assert "imports" in result
    assert "imported_by" in result


def test_imports_forward(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="views.py")
    modules = {i["module"] for i in result["imports"]}
    assert "models" in modules


def test_imports_reverse(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py")
    importers = {i["file"] for i in result["imported_by"]}
    assert "views.py" in importers


def test_imports_excludes_external(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="utils.py")
    # os and json are external, should not appear
    for imp in result["imports"]:
        assert imp.get("external") is not True


def test_imports_include_external(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="utils.py", include_external=True)
    modules = {i["module"] for i in result["imports"]}
    assert "os" in modules or "json" in modules


def test_imports_file_not_found(simple_project):
    idx = Index.build(simple_project)
    with pytest.raises(FileNotFoundError):
        execute(idx, file="nonexistent.py")


def test_imports_depth_1(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="views.py", depth=1)
    # Depth 1: direct imports only, no nested "imports" key
    for imp in result["imports"]:
        assert "imports" not in imp
