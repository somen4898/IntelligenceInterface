from ii_structure.index import Index
from ii_structure.commands.files import execute


def test_files_lists_all(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx)
    assert len(results) == 3
    assert "models.py" in results
    assert "views.py" in results
    assert "utils.py" in results


def test_files_sorted(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx)
    assert results == sorted(results)


def test_files_glob_filter(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, glob_pattern="*model*")
    assert results == ["models.py"]


def test_files_path_prefix(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, path_prefix="mod")
    assert results == ["models.py"]


def test_files_no_match(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, glob_pattern="*.txt")
    assert results == []
