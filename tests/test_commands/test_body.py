import pytest
from ii_structure.index import Index
from ii_structure.commands.body import execute


def test_body_basic(jedi_project):
    idx = Index.build(jedi_project)
    result = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User",
    )
    assert result is not None
    assert "class User" in result["source"]
    assert result["file"] == "models.py"


def test_body_method(jedi_project):
    idx = Index.build(jedi_project)
    result = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User/save",
    )
    assert result is not None
    assert "def save" in result["source"]


def test_body_function(jedi_project):
    idx = Index.build(jedi_project)
    result = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="create_user",
    )
    assert result is not None
    assert "def create_user" in result["source"]
    assert result["file"] == "services.py"


def test_body_with_file_hint(jedi_project):
    idx = Index.build(jedi_project)
    result = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="save",
        file_hint="models.py",
    )
    assert result is not None
    assert result["file"] == "models.py"


def test_body_not_found(jedi_project):
    idx = Index.build(jedi_project)
    result = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="NonExistent",
    )
    assert result is None


def test_body_result_shape(jedi_project):
    idx = Index.build(jedi_project)
    result = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User",
    )
    assert "file" in result
    assert "line" in result
    assert "name" in result
    assert "kind" in result
    assert "source" in result
