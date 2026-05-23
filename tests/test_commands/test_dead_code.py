import textwrap
import pytest
from ii_structure.index import Index


@pytest.fixture
def project_with_dead_code(tmp_path):
    (tmp_path / "app.py").write_text(textwrap.dedent('''\
        def used_function():
            helper()

        def helper():
            return 42

        def dead_function():
            return "nobody calls me"
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


def test_finds_dead_code(project_with_dead_code):
    tmp_path, idx = project_with_dead_code
    from ii_structure.commands.dead_code import execute
    result = execute(idx=idx)
    dead_names = {d["symbol"] for d in result}
    # dead_function is never called
    assert "dead_function" in dead_names
    # helper IS called by used_function
    assert "helper" not in dead_names


def test_dead_code_with_file_filter(project_with_dead_code):
    tmp_path, idx = project_with_dead_code
    from ii_structure.commands.dead_code import execute
    result = execute(idx=idx, file_hint="app.py")
    assert all(d["file"] == "app.py" for d in result)
