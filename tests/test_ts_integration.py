from ii_structure.index import Index


def test_ts_index_builds(ts_project):
    idx = Index.build(ts_project)
    assert any(f.endswith(".ts") for f in idx.files)


def test_ts_outline(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.outline import execute
    result = execute(idx, file="src/models.ts", depth="full")
    names = {s["name"] for s in result["symbols"]}
    assert "User" in names
    assert "BaseService" in names
    assert "formatUser" in names
    assert "log" in names


def test_ts_locate(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.locate import execute
    results = execute(idx, name="UserService", kind="class")
    assert len(results) >= 1
    assert results[0]["file"] == "src/services.ts"


def test_ts_locate_method(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.locate import execute
    results = execute(idx, name="BaseService/log")
    assert len(results) == 1
    assert results[0]["kind"] == "method"


def test_ts_body(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.body import execute
    result = execute(idx=idx, project_root=str(ts_project), name="formatUser")
    assert result is not None
    assert "function formatUser" in result["source"]


def test_ts_search(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.search import execute
    results = execute(idx, query="User")
    assert any(r["name"] == "User" for r in results)


def test_ts_files_summary(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.files import execute
    results = execute(idx, summary=True)
    model_files = [r for r in results if "models.ts" in r["file"]]
    assert len(model_files) >= 1
    assert any("User" in sig for sig in model_files[0]["symbols"])


def test_ts_imports(ts_project):
    idx = Index.build(ts_project)
    from ii_structure.commands.imports import execute
    result = execute(idx, file="src/services.ts", include_external=True)
    modules = {i["module"] for i in result["imports"]}
    assert "./models" in modules


def test_mixed_py_ts_go(tmp_path):
    """A project with .py, .go, and .ts files."""
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "app.py").write_text("def hello():\n    pass\n")
    (tmp_path / "main.go").write_text('package main\n\nfunc main() {}\n')
    (tmp_path / "index.ts").write_text('export function greet(): string { return "hi"; }\n')
    idx = Index.build(tmp_path)
    assert "app.py" in idx.files
    assert "main.go" in idx.files
    assert "index.ts" in idx.files
