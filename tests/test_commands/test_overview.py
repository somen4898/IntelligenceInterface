import textwrap
import pytest
from ii_structure.index import Index


@pytest.fixture
def multi_file_project(tmp_path):
    """Project with multiple files and call relationships."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "models.py").write_text(textwrap.dedent('''\
        class User:
            def save(self):
                print("saving")
            def delete(self):
                print("deleting")
        class Product:
            def save(self):
                print("saving product")
    '''))
    (tmp_path / "src" / "services.py").write_text(textwrap.dedent('''\
        from models import User
        def create_user(name):
            u = User()
            u.save()
            return u
    '''))
    (tmp_path / "src" / "app.py").write_text(textwrap.dedent('''\
        from services import create_user
        def main():
            create_user("test")
    '''))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_services.py").write_text(textwrap.dedent('''\
        from services import create_user
        def test_create():
            create_user("test")
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


def test_overview_returns_structure(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.overview import execute
    result = execute(idx=idx, project_root=str(tmp_path))
    assert "total_files" in result
    assert "structure" in result
    assert "key_files" in result
    assert "entry_points" in result
    assert result["total_files"] >= 3


def test_overview_finds_key_files(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.overview import execute
    result = execute(idx=idx, project_root=str(tmp_path))
    key_file_paths = {f["file"] for f in result["key_files"]}
    # models.py or services.py should be key files (most depended on)
    assert len(key_file_paths) > 0


def test_overview_finds_entry_points(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.overview import execute
    result = execute(idx=idx, project_root=str(tmp_path))
    entry_names = {e["symbol"] for e in result["entry_points"]}
    assert "main" in entry_names


def test_overview_separates_test_files(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.overview import execute
    result = execute(idx=idx, project_root=str(tmp_path))
    assert result["test_files"] >= 1
    assert result["source_files"] >= 3


def test_overview_has_languages(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.overview import execute
    result = execute(idx=idx, project_root=str(tmp_path))
    assert "python" in result["languages"]


def test_files_summary_no_tests(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.files import execute
    result = execute(idx, summary=True, no_tests=True)
    files = [r["file"] for r in result]
    assert not any("test_" in f for f in files)


def test_files_summary_no_private(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.files import execute
    # Add a file with private functions
    (tmp_path / "src" / "utils.py").write_text("def _helper():\n    pass\n\ndef public_func():\n    pass\n")
    idx2 = Index.build(tmp_path)
    result = execute(idx2, summary=True, no_private=True)
    for entry in result:
        for sig in entry.get("symbols", []):
            assert not sig.startswith("def _")


def test_files_summary_skips_empty(multi_file_project):
    tmp_path, idx = multi_file_project
    from ii_structure.commands.files import execute
    # Add an empty __init__.py
    (tmp_path / "src" / "__init__.py").write_text("")
    idx2 = Index.build(tmp_path)
    result = execute(idx2, summary=True)
    files = [r["file"] for r in result]
    assert not any(f.endswith("__init__.py") for f in files)
