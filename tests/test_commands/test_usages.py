import pytest
from ii_structure.index import Index
from ii_structure.commands.usages import execute


def test_usages_basic(jedi_project):
    idx = Index.build(jedi_project)
    results = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User",
    )
    assert len(results) >= 1
    assert all("file" in r for r in results)
    assert all("line" in r for r in results)


def test_usages_with_path_scope(jedi_project):
    idx = Index.build(jedi_project)
    results = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User",
        path_scope="models.py",
    )
    assert all("models" in r["file"] for r in results)


def test_usages_with_limit(jedi_project):
    idx = Index.build(jedi_project)
    results = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User",
        limit=1,
    )
    assert len(results) <= 1


def test_usages_not_found(jedi_project):
    idx = Index.build(jedi_project)
    results = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="DoesNotExist",
    )
    assert results == []


def test_usages_result_has_context(jedi_project):
    idx = Index.build(jedi_project)
    results = execute(
        idx=idx,
        project_root=str(jedi_project),
        name="User",
    )
    if results:
        assert "context" in results[0]
        assert len(results[0]["context"]) > 0
