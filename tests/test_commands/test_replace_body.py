import pathlib
import textwrap

import pytest

from ii_structure.index import Index


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal Python project for write command tests."""
    src = tmp_path / "models.py"
    src.write_text(textwrap.dedent('''\
        class User:
            def __init__(self, name: str):
                self.name = name

            def save(self):
                print("saving")

            def delete(self):
                print("deleting")


        def helper():
            return 42
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def two_file_project(tmp_path):
    """Project with same symbol name in two files."""
    (tmp_path / "models.py").write_text(textwrap.dedent('''\
        class User:
            def save(self):
                print("saving user")
    '''))
    (tmp_path / "product.py").write_text(textwrap.dedent('''\
        class Product:
            def save(self):
                print("saving product")
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


def test_replace_simple_method(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    new_body = textwrap.dedent('''\
        def save(self):
            self.validate()
            self.db.update(self.to_dict())
            return True
    ''').rstrip("\n")

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        name="User/save",
        new_body=new_body,
    )

    assert result["file"] == "models.py"
    assert result["symbol"] == "User/save"
    assert result["lines_removed"] == 2
    assert result["lines_added"] == 4

    content = (tmp_path / "models.py").read_text()
    assert "self.validate()" in content
    assert "self.db.update(self.to_dict())" in content
    # Original save body should be gone
    assert 'print("saving")' not in content
    # Other methods should be preserved
    assert 'print("deleting")' in content


def test_replace_preserves_indentation(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    # New body with NO indentation — should be re-indented to match method level
    new_body = "def save(self):\n    return True"

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        name="User/save",
        new_body=new_body,
    )

    content = (tmp_path / "models.py").read_text()
    lines = content.splitlines()
    # Find the save method line
    save_lines = [l for l in lines if "def save" in l]
    assert len(save_lines) == 1
    # Should be indented at method level (4 spaces)
    assert save_lines[0].startswith("    def save")
    # Body should be indented 8 spaces
    return_lines = [l for l in lines if "return True" in l]
    assert len(return_lines) == 1
    assert return_lines[0].startswith("        return True")


def test_replace_top_level_function(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    new_body = "def helper():\n    return 99"

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        name="helper",
        new_body=new_body,
    )

    assert result["file"] == "models.py"
    content = (tmp_path / "models.py").read_text()
    assert "return 99" in content
    assert "return 42" not in content
    # Class should be untouched
    assert "class User:" in content


def test_replace_updates_index(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    new_body = "def save(self):\n    return True\n    # extra line\n    # another"

    execute(
        idx=idx,
        project_root=str(tmp_path),
        name="User/save",
        new_body=new_body,
    )

    # Index should be refreshed — search should still find save
    results = idx.search_symbols("User/save")
    assert len(results) == 1
    # The line range should reflect the new body
    sym = results[0]
    assert sym["name"] == "save"


def test_replace_ambiguous_symbol_errors(two_file_project):
    tmp_path, idx = two_file_project
    from ii_structure.commands.replace_body import execute

    with pytest.raises(Exception, match="Multiple definitions found"):
        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="save",
            new_body="def save(self):\n    pass",
        )


def test_replace_with_file_hint(two_file_project):
    tmp_path, idx = two_file_project
    from ii_structure.commands.replace_body import execute

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        name="save",
        new_body="def save(self):\n    return 'updated'",
        file_hint="models.py",
    )

    assert result["file"] == "models.py"
    content = (tmp_path / "models.py").read_text()
    assert "return 'updated'" in content
    # Other file untouched
    product_content = (tmp_path / "product.py").read_text()
    assert 'print("saving product")' in product_content


def test_replace_symbol_not_found(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    with pytest.raises(Exception, match="not found"):
        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="nonexistent",
            new_body="def foo():\n    pass",
        )


def test_replace_empty_body_errors(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    with pytest.raises(Exception, match="[Ee]mpty"):
        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="User/save",
            new_body="",
        )
