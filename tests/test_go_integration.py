from ii_structure.index import Index


def test_go_index_builds(go_project):
    idx = Index.build(go_project)
    assert any(f.endswith(".go") for f in idx.files)


def test_go_outline(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.outline import execute
    result = execute(idx, file="server/server.go", depth="full")
    names = {s["name"] for s in result["symbols"]}
    assert "Server" in names
    assert "NewServer" in names
    assert "Start" in names


def test_go_locate(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.locate import execute
    results = execute(idx, name="Server", kind="class")
    assert len(results) >= 1
    assert results[0]["file"] == "server/server.go"


def test_go_locate_method(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.locate import execute
    results = execute(idx, name="Server/Start")
    assert len(results) == 1
    assert results[0]["kind"] == "method"


def test_go_body(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.body import execute
    result = execute(idx=idx, project_root=str(go_project), name="NewServer")
    assert result is not None
    assert "func NewServer" in result["source"]


def test_go_search(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.search import execute
    results = execute(idx, query="Server")
    assert any(r["name"] == "Server" for r in results)


def test_go_files_summary(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.files import execute
    results = execute(idx, summary=True)
    server_files = [r for r in results if "server.go" in r["file"]]
    assert len(server_files) >= 1
    assert any("Server" in sig for sig in server_files[0]["symbols"])


def test_go_imports(go_project):
    idx = Index.build(go_project)
    from ii_structure.commands.imports import execute
    result = execute(idx, file="main.go", include_external=True)
    modules = {i["module"] for i in result["imports"]}
    assert "fmt" in modules


def test_mixed_project(tmp_path):
    """A project with both .py and .go files."""
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "app.py").write_text("def hello():\n    pass\n")
    (tmp_path / "main.go").write_text('package main\n\nfunc main() {}\n')
    idx = Index.build(tmp_path)
    assert "app.py" in idx.files
    assert "main.go" in idx.files
