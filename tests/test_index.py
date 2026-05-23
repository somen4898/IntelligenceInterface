import time
from ii_structure.index import Index


def test_build_index(simple_project):
    idx = Index.build(simple_project)
    assert len(idx.files) == 3  # models.py, views.py, utils.py
    assert "models.py" in idx.files
    assert "views.py" in idx.files
    assert "utils.py" in idx.files


def test_index_stores_symbols(simple_project):
    idx = Index.build(simple_project)
    models = idx.files["models.py"]
    symbol_names = {s["name"] for s in models["symbols"]}
    assert "User" in symbol_names
    assert "Product" in symbol_names
    assert "MAX_USERS" in symbol_names


def test_index_stores_imports(simple_project):
    idx = Index.build(simple_project)
    views = idx.files["views.py"]
    modules = {i["module"] for i in views["imports"]}
    assert "models" in modules


def test_save_and_load(simple_project, tmp_path):
    idx = Index.build(simple_project)
    state_dir = tmp_path / ".ii-structure"
    idx.save(state_dir)

    loaded = Index.load(state_dir)
    assert loaded.files.keys() == idx.files.keys()
    assert loaded.project_root == idx.project_root


def test_staleness_detection(tmp_path):
    # Create a file
    py_file = tmp_path / "example.py"
    py_file.write_text("def hello():\n    pass\n")
    (tmp_path / "pyproject.toml").touch()

    idx = Index.build(tmp_path)
    state_dir = tmp_path / ".ii-structure"
    idx.save(state_dir)

    # Modify the file
    time.sleep(0.05)
    py_file.write_text("def hello():\n    pass\n\ndef goodbye():\n    pass\n")

    loaded = Index.load(state_dir)
    loaded.refresh(tmp_path)
    funcs = [s for s in loaded.files["example.py"]["symbols"] if s["kind"] == "function"]
    assert len(funcs) == 2


def test_deleted_file_removed(tmp_path):
    py_file = tmp_path / "temp.py"
    py_file.write_text("x = 1\n")
    (tmp_path / "pyproject.toml").touch()

    idx = Index.build(tmp_path)
    state_dir = tmp_path / ".ii-structure"
    idx.save(state_dir)

    py_file.unlink()

    loaded = Index.load(state_dir)
    loaded.refresh(tmp_path)
    assert "temp.py" not in loaded.files


def test_new_file_added(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "first.py").write_text("a = 1\n")

    idx = Index.build(tmp_path)
    state_dir = tmp_path / ".ii-structure"
    idx.save(state_dir)

    (tmp_path / "second.py").write_text("b = 2\n")

    loaded = Index.load(state_dir)
    loaded.refresh(tmp_path)
    assert "second.py" in loaded.files


def test_parse_error_recorded(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "bad.py").write_text("def broken(\n")

    idx = Index.build(tmp_path)
    assert idx.files["bad.py"]["parse_error"] is not None
    assert idx.files["bad.py"]["symbols"] == []


def test_skips_venv(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "main.py").write_text("x = 1\n")
    venv = tmp_path / "venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "something.py").write_text("y = 2\n")

    idx = Index.build(tmp_path)
    assert len(idx.files) == 1
    assert "main.py" in idx.files


def test_respects_gitignore(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / ".gitignore").write_text("ignored/\n")
    (tmp_path / "main.py").write_text("x = 1\n")
    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "secret.py").write_text("y = 2\n")

    idx = Index.build(tmp_path)
    assert "main.py" in idx.files
    assert "ignored/secret.py" not in idx.files


def test_get_symbols_for_file(simple_project):
    idx = Index.build(simple_project)
    symbols = idx.get_symbols("models.py")
    assert any(s["name"] == "User" for s in symbols)


def test_search_symbols(simple_project):
    idx = Index.build(simple_project)
    results = idx.search_symbols("User")
    assert len(results) >= 1
    assert results[0]["name"] == "User"


def test_search_symbols_by_name_path(simple_project):
    idx = Index.build(simple_project)
    results = idx.search_symbols("User/save")
    assert len(results) == 1
    assert results[0]["name"] == "save"
    assert results[0]["parent"] == "User"
