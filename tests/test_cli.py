import sys
import yaml
import subprocess
import pytest


def run_cli(*args, cwd=None):
    result = subprocess.run(
        [sys.executable, "-m", "ii_structure.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


@pytest.fixture
def project_with_root(simple_project, tmp_path):
    """Copy fixture to tmp_path with a pyproject.toml so root detection works."""
    dest = tmp_path / "project"
    dest.mkdir()
    (dest / "pyproject.toml").write_text('[project]\nname = "test"\n')
    for f in simple_project.iterdir():
        if f.is_file():
            (dest / f.name).write_text(f.read_text())
    return dest


def test_outline_command(project_with_root):
    result = run_cli("outline", "models.py", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "outline"
    names = {s["name"] for s in parsed["result"]["symbols"]}
    assert "User" in names


def test_outline_with_depth(project_with_root):
    result = run_cli("outline", "models.py", "--depth", "full", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    names = {s["name"] for s in parsed["result"]["symbols"]}
    assert "save" in names


def test_outline_with_kind(project_with_root):
    result = run_cli("outline", "models.py", "--kind", "class", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert all(s["kind"] == "class" for s in parsed["result"]["symbols"])


def test_locate_command(project_with_root):
    result = run_cli("locate", "User", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "locate"
    assert len(parsed["result"]) >= 1
    assert parsed["result"][0]["name"] == "User"


def test_locate_with_kind(project_with_root):
    result = run_cli("locate", "User", "--kind", "class", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert len(parsed["result"]) == 1


def test_locate_not_found(project_with_root):
    result = run_cli("locate", "NonExistent", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["result"] == []


def test_outline_file_not_found(project_with_root):
    result = run_cli("outline", "nope.py", cwd=project_with_root)
    assert result.returncode == 1
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is False
    assert "not found" in parsed["error"].lower()


def test_project_flag(project_with_root):
    # Run from a different directory but point --project at the right one
    result = run_cli(
        "--project", str(project_with_root),
        "locate", "User",
    )
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True


def test_no_cache_flag(project_with_root):
    # First run builds cache
    run_cli("locate", "User", cwd=project_with_root)
    assert (project_with_root / ".ii-structure" / "graph.db").exists()

    # Second run with --no-cache rebuilds
    result = run_cli("--no-cache", "locate", "User", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True


def test_usages_command(project_with_root):
    result = run_cli("usages", "User", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "usages"


def test_usages_with_limit(project_with_root):
    result = run_cli("usages", "User", "--limit", "1", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert len(parsed["result"]) <= 1


def test_body_command(project_with_root):
    result = run_cli("body", "User", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "body"
    assert "source" in parsed["result"]


def test_body_not_found_cli(project_with_root):
    result = run_cli("body", "NonExistent", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is False


def test_body_with_file(project_with_root):
    result = run_cli("body", "save", "--file", "models.py", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["result"]["file"] == "models.py"


def test_files_command(project_with_root):
    result = run_cli("files", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "files"
    assert len(parsed["result"]) >= 1


def test_search_command(project_with_root):
    result = run_cli("search", "User", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "search"
    assert len(parsed["result"]) >= 1


def test_help_command(project_with_root):
    result = run_cli("help", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert "commands" in parsed["result"]
    assert "workflow" in parsed["result"]


def test_help_single_command_cli(project_with_root):
    result = run_cli("help", "outline", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["result"]["command"] == "outline"


def test_imports_command(project_with_root):
    result = run_cli("imports", "views.py", cwd=project_with_root)
    assert result.returncode == 0
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
    assert parsed["command"] == "imports"


def test_init_creates_claude_md(project_with_root):
    result = run_cli("init", cwd=project_with_root)
    assert result.returncode == 0
    claude_md = project_with_root / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "ii-structure" in content
    assert "files --summary" in content
    assert "outline" in content


def test_init_appends_to_existing(project_with_root):
    claude_md = project_with_root / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nExisting instructions.\n")
    result = run_cli("init", cwd=project_with_root)
    assert result.returncode == 0
    content = claude_md.read_text()
    assert "My Project" in content  # original content preserved
    assert "ii-structure" in content  # new content added


def test_init_skips_if_already_present(project_with_root):
    claude_md = project_with_root / "CLAUDE.md"
    claude_md.write_text("# ii-structure\nAlready configured.\n")
    result = run_cli("init", cwd=project_with_root)
    assert "already exists" in result.stdout.lower()
