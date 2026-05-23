from ii_structure.index import Index
from ii_structure.commands.locate import execute


def test_locate_by_name(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User")
    assert len(results) == 1
    assert results[0]["name"] == "User"
    assert results[0]["kind"] == "class"
    assert results[0]["file"] == "models.py"


def test_locate_by_name_path(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User/save")
    assert len(results) == 1
    assert results[0]["name"] == "save"
    assert results[0]["kind"] == "method"


def test_locate_returns_multiple(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="save")
    # User.save and Product.save
    assert len(results) == 2


def test_locate_with_kind_filter(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User", kind="class")
    assert len(results) == 1
    assert results[0]["kind"] == "class"


def test_locate_with_file_filter(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="save", file="models.py")
    assert all(r["file"] == "models.py" for r in results)


def test_locate_anchored(simple_project):
    idx = Index.build(simple_project)
    # /User means top-level only
    results = execute(idx, name="/User")
    assert len(results) == 1
    assert results[0]["parent"] is None


def test_locate_substring(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="load", match="substring")
    assert any(r["name"] == "load_config" for r in results)


def test_locate_not_found(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="NonExistent")
    assert results == []


def test_locate_result_shape(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User")
    r = results[0]
    assert "file" in r
    assert "line" in r
    assert "kind" in r
    assert "name" in r
    assert "signature" in r
