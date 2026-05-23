import pytest
from ii_structure.root import find_project_root


def test_finds_pyproject_toml(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    sub = tmp_path / "src" / "pkg"
    sub.mkdir(parents=True)
    assert find_project_root(sub) == tmp_path


def test_finds_setup_py(tmp_path):
    (tmp_path / "setup.py").touch()
    sub = tmp_path / "src"
    sub.mkdir()
    assert find_project_root(sub) == tmp_path


def test_finds_setup_cfg(tmp_path):
    (tmp_path / "setup.cfg").touch()
    assert find_project_root(tmp_path) == tmp_path


def test_finds_git_dir(tmp_path):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "deep" / "nested"
    sub.mkdir(parents=True)
    assert find_project_root(sub) == tmp_path


def test_pyproject_takes_priority_over_git(tmp_path):
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "subproject"
    inner.mkdir()
    (inner / "pyproject.toml").touch()
    assert find_project_root(inner) == inner


def test_raises_when_no_root(tmp_path):
    isolated = tmp_path / "nowhere"
    isolated.mkdir()
    with pytest.raises(FileNotFoundError):
        find_project_root(isolated)
