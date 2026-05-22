import pytest
from ii_structure.resolver import get_definition_source
from ii_structure.index import Index


@pytest.fixture
def jedi_idx(jedi_project):
    return Index.build(jedi_project)


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
