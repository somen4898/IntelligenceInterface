import pathlib
import pytest
from ii_structure.resolver import find_usages, get_definition_source
from ii_structure.index import Index


@pytest.fixture
def jedi_idx(jedi_project):
    return Index.build(jedi_project)


# --- find_usages tests ---

def test_find_usages_basic(jedi_project, jedi_idx):
    """Should find at least the definition of User."""
    results = find_usages(
        project_root=str(jedi_project),
        name="User",
        index=jedi_idx,
    )
    assert len(results) >= 1
    assert any(r["file"] == "models.py" for r in results)


def test_find_usages_with_path_scope(jedi_project, jedi_idx):
    """Scope to a specific file."""
    results = find_usages(
        project_root=str(jedi_project),
        name="User",
        index=jedi_idx,
        path_scope="models.py",
    )
    assert all(r["file"].startswith("models") for r in results)


def test_find_usages_with_limit(jedi_project, jedi_idx):
    results = find_usages(
        project_root=str(jedi_project),
        name="User",
        index=jedi_idx,
        limit=2,
    )
    assert len(results) <= 2


def test_find_usages_not_found(jedi_project, jedi_idx):
    results = find_usages(
        project_root=str(jedi_project),
        name="NonExistent",
        index=jedi_idx,
    )
    assert results == []


def test_find_usages_result_shape(jedi_project, jedi_idx):
    results = find_usages(
        project_root=str(jedi_project),
        name="User",
        index=jedi_idx,
    )
    assert len(results) >= 1
    r = results[0]
    assert "file" in r
    assert "line" in r
    assert "kind" in r
    assert "context" in r


# --- get_definition_source tests ---

def test_get_definition_source_basic(jedi_project, jedi_idx):
    result = get_definition_source(
        project_root=str(jedi_project),
        name="User",
        index=jedi_idx,
    )
    assert result is not None
    assert "class User" in result["source"]
    assert result["file"] == "models.py"
    assert result["line"] > 0


def test_get_definition_source_method(jedi_project, jedi_idx):
    result = get_definition_source(
        project_root=str(jedi_project),
        name="User/save",
        index=jedi_idx,
    )
    assert result is not None
    assert "def save" in result["source"]


def test_get_definition_source_with_file_hint(jedi_project, jedi_idx):
    result = get_definition_source(
        project_root=str(jedi_project),
        name="save",
        index=jedi_idx,
        file_hint="models.py",
    )
    assert result is not None
    assert result["file"] == "models.py"


def test_get_definition_source_not_found(jedi_project, jedi_idx):
    result = get_definition_source(
        project_root=str(jedi_project),
        name="NonExistent",
        index=jedi_idx,
    )
    assert result is None


def test_get_definition_source_result_shape(jedi_project, jedi_idx):
    result = get_definition_source(
        project_root=str(jedi_project),
        name="User",
        index=jedi_idx,
    )
    assert "file" in result
    assert "line" in result
    assert "name" in result
    assert "kind" in result
    assert "source" in result
