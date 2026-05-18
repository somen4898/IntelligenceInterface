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


def test_files_summary(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, summary=True)
    assert len(results) == 3
    # Each entry should have file and symbols
    for entry in results:
        assert "file" in entry
        assert "symbols" in entry
        assert isinstance(entry["symbols"], list)


def test_files_summary_has_signatures(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, summary=True)
    models = [r for r in results if r["file"] == "models.py"][0]
    # Should have User and Product class signatures and MAX_USERS
    sigs = " ".join(models["symbols"])
    assert "User" in sigs
    assert "Product" in sigs


def test_files_summary_top_level_only(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, summary=True)
    models = [r for r in results if r["file"] == "models.py"][0]
    sigs = " ".join(models["symbols"])
    # Methods like save/delete should NOT appear (they have parents)
    assert "def save" not in sigs
    assert "def delete" not in sigs


def test_files_summary_with_path_filter(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, summary=True, path_prefix="mod")
    assert len(results) == 1
    assert results[0]["file"] == "models.py"
