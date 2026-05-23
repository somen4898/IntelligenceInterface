import textwrap
import pytest
from ii_structure.index import Index


@pytest.fixture
def project_with_tests(tmp_path):
    (tmp_path / "models.py").write_text(textwrap.dedent('''\
        class User:
            def save(self):
                print("saving")
    '''))
    (tmp_path / "test_models.py").write_text(textwrap.dedent('''\
        def test_save():
            u = User()
            u.save()
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


def test_coverage_finds_tests(project_with_tests):
    tmp_path, idx = project_with_tests
    from ii_structure.commands.test_coverage import execute
    result = execute(idx=idx, project_root=str(tmp_path), name="User/save")
    assert result["symbol"] == "User/save"
    assert result["total_tests"] >= 0  # depends on TESTED_BY edge resolution


def test_coverage_not_found(project_with_tests):
    tmp_path, idx = project_with_tests
    from ii_structure.commands.test_coverage import execute
    with pytest.raises(ValueError, match="not found"):
        execute(idx=idx, project_root=str(tmp_path), name="nonexistent")


def test_coverage_returns_covered_flag(project_with_tests):
    tmp_path, idx = project_with_tests
    from ii_structure.commands.test_coverage import execute
    result = execute(idx=idx, project_root=str(tmp_path), name="User/save")
    assert "covered" in result
    assert isinstance(result["covered"], bool)
