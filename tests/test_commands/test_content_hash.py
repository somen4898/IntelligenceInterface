"""Tests for content_hash on body and --expect-hash on write commands."""
import textwrap

import pytest

from ii_structure.index import Index


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal Python project for hash tests."""
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


# --- body returns content_hash ---

def test_body_returns_content_hash(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.body import execute

    result = execute(idx=idx, project_root=str(tmp_path), name="User/save")
    assert result is not None
    assert "content_hash" in result
    assert result["content_hash"].startswith("sha256:")


def test_body_hash_changes_when_file_changes(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.body import execute

    result1 = execute(idx=idx, project_root=str(tmp_path), name="User/save")
    hash1 = result1["content_hash"]

    # Modify the file
    f = tmp_path / "models.py"
    content = f.read_text()
    f.write_text(content + "\n# comment\n")

    # Rebuild index to pick up the change
    idx2 = Index.build(tmp_path)
    result2 = execute(idx=idx2, project_root=str(tmp_path), name="User/save")
    hash2 = result2["content_hash"]

    assert hash1 != hash2


def test_body_hash_stable_for_same_file(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.body import execute

    result1 = execute(idx=idx, project_root=str(tmp_path), name="User/save")
    result2 = execute(idx=idx, project_root=str(tmp_path), name="User/delete")

    # Same file, same hash
    assert result1["content_hash"] == result2["content_hash"]


# --- replace-body with --expect-hash ---

def test_replace_body_with_matching_hash(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.body import execute as body_execute
    from ii_structure.commands.replace_body import execute as replace_execute

    # Get hash from body
    body_result = body_execute(idx=idx, project_root=str(tmp_path), name="User/save")
    content_hash = body_result["content_hash"]

    # Replace with matching hash — should succeed
    result = replace_execute(
        idx=idx,
        project_root=str(tmp_path),
        name="User/save",
        new_body="def save(self):\n    return True",
        expect_hash=content_hash,
    )
    assert result["file"] == "models.py"


def test_replace_body_with_wrong_hash(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    with pytest.raises(Exception, match="[Ff]ile has changed|hash.*mismatch|stale"):
        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="User/save",
            new_body="def save(self):\n    return True",
            expect_hash="sha256:wronghash",
        )


def test_replace_body_without_hash_still_works(tmp_project):
    """Backward compatibility — omitting hash should work as before."""
    tmp_path, idx = tmp_project
    from ii_structure.commands.replace_body import execute

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        name="User/save",
        new_body="def save(self):\n    return True",
    )
    assert result["file"] == "models.py"


def test_replace_body_hash_detects_concurrent_edit(tmp_project):
    """Simulate: agent reads body, another tool edits the file, agent tries to write."""
    tmp_path, idx = tmp_project
    from ii_structure.commands.body import execute as body_execute
    from ii_structure.commands.replace_body import execute as replace_execute

    # Agent reads body and gets hash
    body_result = body_execute(idx=idx, project_root=str(tmp_path), name="User/save")
    content_hash = body_result["content_hash"]

    # Another tool modifies the file
    f = tmp_path / "models.py"
    content = f.read_text()
    f.write_text(content.replace('print("saving")', 'print("updated by another tool")'))

    # Agent tries to write with the old hash — should fail
    with pytest.raises(Exception, match="[Ff]ile has changed|hash.*mismatch|stale"):
        replace_execute(
            idx=idx,
            project_root=str(tmp_path),
            name="User/save",
            new_body="def save(self):\n    return True",
            expect_hash=content_hash,
        )


# --- insert-symbol with --expect-hash ---

def test_insert_symbol_with_matching_hash(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.body import execute as body_execute
    from ii_structure.commands.insert_symbol import execute as insert_execute

    body_result = body_execute(idx=idx, project_root=str(tmp_path), name="User/save")
    content_hash = body_result["content_hash"]

    result = insert_execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="after",
        new_code="def validate(self):\n    pass",
        expect_hash=content_hash,
    )
    assert result["file"] == "models.py"


def test_insert_symbol_with_wrong_hash(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    with pytest.raises(Exception, match="[Ff]ile has changed|hash.*mismatch|stale"):
        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="User/save",
            position="after",
            new_code="def validate(self):\n    pass",
            expect_hash="sha256:wronghash",
        )


def test_insert_symbol_without_hash_still_works(tmp_project):
    tmp_path, idx = tmp_project
    from ii_structure.commands.insert_symbol import execute

    result = execute(
        idx=idx,
        project_root=str(tmp_path),
        anchor="User/save",
        position="after",
        new_code="def validate(self):\n    pass",
    )
    assert result["file"] == "models.py"
