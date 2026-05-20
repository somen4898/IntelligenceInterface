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


def test_insert_after_method(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    new_code = "def validate(self):\n    if not self.name:\n        raise ValueError('name required')"

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="after",
        new_code=new_code,
    )

    assert result["file"] == "models.py"
    assert result["anchor"] == "User/save"
    assert result["position"] == "after"
    assert result["lines_added"] == 3

    content = (tmp_path / "models.py").read_text()
    lines = content.splitlines()

    # Find positions of save, validate, delete
    save_end = None
    validate_start = None
    delete_start = None
    for i, line in enumerate(lines):
        if "def save" in line:
            save_end = i  # will be updated
        if 'print("saving")' in line:
            save_end = i
        if "def validate" in line:
            validate_start = i
        if "def delete" in line:
            delete_start = i

    assert validate_start is not None, f"validate not found in:\n{content}"
    assert save_end < validate_start < delete_start


def test_insert_before_method(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    new_code = "def pre_save(self):\n    self.validate()"

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="before",
        new_code=new_code,
    )

    assert result["position"] == "before"

    content = (tmp_path / "models.py").read_text()
    lines = content.splitlines()

    pre_save_line = None
    save_line = None
    for i, line in enumerate(lines):
        if "def pre_save" in line:
            pre_save_line = i
        if "def save" in line and "pre_save" not in line:
            save_line = i

    assert pre_save_line is not None
    assert pre_save_line < save_line


def test_insert_after_last_method(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    new_code = "def to_dict(self):\n    return {'name': self.name}"

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/delete",
        position="after",
        new_code=new_code,
    )

    content = (tmp_path / "models.py").read_text()
    assert "def to_dict" in content

    lines = content.splitlines()
    delete_line = None
    to_dict_line = None
    helper_line = None
    for i, line in enumerate(lines):
        if "def delete" in line:
            delete_line = i
        if "def to_dict" in line:
            to_dict_line = i
        if "def helper" in line:
            helper_line = i

    assert delete_line < to_dict_line
    # to_dict should be inside the class, before helper
    assert to_dict_line < helper_line


def test_insert_after_top_level(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    new_code = "def another_helper():\n    return 99"

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="helper",
        position="after",
        new_code=new_code,
    )

    content = (tmp_path / "models.py").read_text()
    assert "def another_helper" in content

    lines = content.splitlines()
    helper_line = None
    another_line = None
    for i, line in enumerate(lines):
        if "def helper" in line and "another" not in line:
            helper_line = i
        if "def another_helper" in line:
            another_line = i

    assert helper_line < another_line
    # Top-level function — no indentation
    assert lines[another_line].startswith("def another_helper")


def test_insert_preserves_indentation(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    # Unindented new code — should get indented to match anchor's level
    new_code = "def check(self):\n    return True"

    execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="after",
        new_code=new_code,
    )

    content = (tmp_path / "models.py").read_text()
    lines = content.splitlines()
    check_lines = [l for l in lines if "def check" in l]
    assert len(check_lines) == 1
    # Should be indented at method level (4 spaces)
    assert check_lines[0].startswith("    def check")


def test_insert_adds_blank_line_separator(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    new_code = "def check(self):\n    return True"

    execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="after",
        new_code=new_code,
    )

    content = (tmp_path / "models.py").read_text()
    lines = content.splitlines()

    # Find check method
    check_idx = None
    for i, line in enumerate(lines):
        if "def check" in line:
            check_idx = i
            break

    assert check_idx is not None
    # Line before check should be blank (separator)
    assert lines[check_idx - 1].strip() == ""


def test_insert_updates_index(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    new_code = "def validate(self):\n    pass"

    execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="after",
        new_code=new_code,
    )

    # Index should be refreshed — search should find the new symbol
    results = idx.search_symbols("User/validate")
    assert len(results) == 1
    assert results[0]["name"] == "validate"
