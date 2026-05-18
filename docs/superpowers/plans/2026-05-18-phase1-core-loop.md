# Phase 1: Core Loop — Parser, Index, Outline, Locate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working `ii-structure` CLI with `outline` and `locate` commands — enough to prove the core loop of parse → index → query → YAML output.

**Architecture:** `cli.py` (click) dispatches to command modules. `parser.py` extracts symbols/imports from Python files using stdlib `ast`. `index.py` builds/loads/updates a JSON index with staleness detection. `output.py` formats all results as YAML envelopes. Two commands (`outline`, `locate`) exercise the full pipeline.

**Tech Stack:** Python 3.10+, click, pyyaml, pathspec, pytest

---

### File Map

```
ii-structure/
├── pyproject.toml                    # package metadata, console script entry
├── src/
│   └── ii_structure/
│       ├── __init__.py               # version string
│       ├── cli.py                    # click group + global options
│       ├── parser.py                 # ast-based symbol/import extraction
│       ├── index.py                  # build, load, staleness, update
│       ├── output.py                 # YAML envelope formatting
│       ├── root.py                   # project root detection
│       └── commands/
│           ├── __init__.py
│           ├── outline.py            # file skeleton command
│           └── locate.py             # symbol finder command
├── tests/
│   ├── conftest.py                   # shared fixtures
│   ├── test_parser.py
│   ├── test_index.py
│   ├── test_output.py
│   ├── test_root.py
│   ├── fixtures/
│   │   └── simple_project/
│   │       ├── models.py
│   │       ├── views.py
│   │       └── utils.py
│   └── test_commands/
│       ├── test_outline.py
│       └── test_locate.py
└── .gitignore
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/ii_structure/__init__.py`
- Create: `.gitignore`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/somen/Projects/ii-structure
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ii-structure"
version = "0.1.0"
description = "Structural code navigation CLI for LLM agents"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "pyyaml>=6.0",
    "pathspec>=0.11",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[project.scripts]
ii-structure = "ii_structure.cli:main"
```

- [ ] **Step 3: Create __init__.py**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.ii-structure/
.venv/
venv/
.pytest_cache/
```

- [ ] **Step 5: Create empty conftest.py**

```python
import pathlib
import pytest


@pytest.fixture
def fixtures_dir():
    return pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_project(fixtures_dir):
    return fixtures_dir / "simple_project"
```

- [ ] **Step 6: Create test fixture files**

Create `tests/fixtures/simple_project/models.py`:

```python
"""Data models for the application."""

from dataclasses import dataclass


@dataclass
class User:
    """A user in the system."""
    name: str
    email: str

    def save(self) -> None:
        """Persist the user."""
        pass

    def delete(self) -> None:
        """Remove the user."""
        pass


@dataclass
class Product:
    """A product listing."""
    title: str
    price: float

    def save(self) -> None:
        """Persist the product."""
        pass


MAX_USERS = 100
```

Create `tests/fixtures/simple_project/views.py`:

```python
"""View handlers."""

from models import User, Product


def get_user(user_id: int) -> User:
    """Fetch a user by ID."""
    return User(name="test", email="test@test.com")


def list_products() -> list[Product]:
    """List all products."""
    return []


async def async_handler(request) -> dict:
    """An async view handler."""
    user = get_user(request.user_id)
    return {"user": user.name}
```

Create `tests/fixtures/simple_project/utils.py`:

```python
"""Utility functions."""

import os
import json
from typing import Any


def load_config(path: str) -> dict[str, Any]:
    """Load a JSON config file."""
    with open(path) as f:
        return json.load(f)


class Singleton:
    """A singleton base class."""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class ConfigManager(Singleton):
    """Manages application configuration."""

    def __init__(self):
        self.data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        """Get a config value."""
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set a config value."""
        self.data[key] = value
```

- [ ] **Step 7: Install in dev mode and verify**

```bash
cd /Users/somen/Projects/ii-structure
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: installs successfully, `ii-structure --help` will fail (no cli.py yet — that's fine).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/ tests/ .gitignore
git commit -m "feat: project scaffold with fixtures and dev setup"
```

---

### Task 2: Output Module

**Files:**
- Create: `src/ii_structure/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_output.py`:

```python
import yaml
from ii_structure.output import format_success, format_error


def test_format_success_basic():
    result = format_success("locate", [{"file": "a.py", "line": 1}])
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is True
    assert parsed["command"] == "locate"
    assert parsed["result"] == [{"file": "a.py", "line": 1}]


def test_format_success_empty_result():
    result = format_success("files", [])
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is True
    assert parsed["result"] == []


def test_format_error_basic():
    result = format_error("locate", "Symbol not found")
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is False
    assert parsed["command"] == "locate"
    assert parsed["error"] == "Symbol not found"
    assert "suggestion" not in parsed


def test_format_error_with_suggestion():
    result = format_error("locate", "Not found", suggestion="Try 'User'")
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is False
    assert parsed["suggestion"] == "Try 'User'"


def test_format_success_truncated():
    items = [{"name": f"sym{i}"} for i in range(30)]
    result = format_success("search", items, total=100, limit=30)
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is True
    assert parsed["total"] == 100
    assert parsed["truncated"] is True
    assert parsed["limit"] == 30
    assert len(parsed["result"]) == 30


def test_output_is_valid_yaml():
    result = format_success("outline", {"file": "test.py", "symbols": []})
    parsed = yaml.safe_load(result)
    assert isinstance(parsed, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/somen/Projects/ii-structure
pytest tests/test_output.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ii_structure.output'`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/output.py`:

```python
import yaml
from typing import Any


def format_success(
    command: str,
    result: Any,
    total: int | None = None,
    limit: int | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "ok": True,
        "command": command,
        "result": result,
    }
    if total is not None and limit is not None:
        envelope["total"] = total
        envelope["truncated"] = True
        envelope["limit"] = limit
    return yaml.dump(envelope, default_flow_style=False, sort_keys=False)


def format_error(
    command: str,
    error: str,
    suggestion: str | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "ok": False,
        "command": command,
        "error": error,
    }
    if suggestion is not None:
        envelope["suggestion"] = suggestion
    return yaml.dump(envelope, default_flow_style=False, sort_keys=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_output.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/output.py tests/test_output.py
git commit -m "feat: YAML output envelope formatting"
```

---

### Task 3: Project Root Detection

**Files:**
- Create: `src/ii_structure/root.py`
- Create: `tests/test_root.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_root.py`:

```python
import pathlib
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_root.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/root.py`:

```python
import pathlib

MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", ".git")


def find_project_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    while True:
        for marker in MARKERS:
            candidate = current / marker
            if candidate.exists():
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"No project root found from {start}. "
        "Looked for: pyproject.toml, setup.py, setup.cfg, .git. "
        "Use --project to specify the root."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_root.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/root.py tests/test_root.py
git commit -m "feat: project root detection"
```

---

### Task 4: Parser Module

**Files:**
- Create: `src/ii_structure/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_parser.py`:

```python
import pytest
from ii_structure.parser import parse_file


SIMPLE_CLASS = '''\
"""Module docstring."""

from dataclasses import dataclass


@dataclass
class User:
    """A user in the system."""
    name: str
    email: str

    def save(self) -> None:
        """Persist the user."""
        pass

    def delete(self) -> None:
        """Remove the user."""
        pass


MAX_USERS = 100
'''

SIMPLE_FUNCTION = '''\
import os
from typing import Any


def load_config(path: str) -> dict[str, Any]:
    """Load a JSON config file."""
    with open(path) as f:
        return {}
'''

ASYNC_FUNCTION = '''\
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    pass
'''

NESTED_CLASSES = '''\
class Outer:
    """Outer class."""

    class Inner:
        """Inner class."""

        def inner_method(self):
            pass

    def outer_method(self):
        pass
'''

SYNTAX_ERROR = '''\
def broken(
    this is not valid python
'''

EMPTY_FILE = ''


# --- Symbol extraction tests ---

def test_extracts_class():
    result = parse_file("test.py", SIMPLE_CLASS)
    assert result.error is None
    classes = [s for s in result.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "User"
    assert classes[0].docstring == "A user in the system."
    assert "dataclass" in classes[0].signature


def test_extracts_methods():
    result = parse_file("test.py", SIMPLE_CLASS)
    methods = [s for s in result.symbols if s.kind == "method"]
    assert len(methods) == 2
    names = {m.name for m in methods}
    assert names == {"save", "delete"}
    assert all(m.parent == "User" for m in methods)


def test_extracts_function():
    result = parse_file("test.py", SIMPLE_FUNCTION)
    functions = [s for s in result.symbols if s.kind == "function"]
    assert len(functions) == 1
    assert functions[0].name == "load_config"
    assert "path: str" in functions[0].signature
    assert "dict[str, Any]" in functions[0].signature
    assert functions[0].docstring == "Load a JSON config file."


def test_extracts_async_function():
    result = parse_file("test.py", ASYNC_FUNCTION)
    functions = [s for s in result.symbols if s.kind == "function"]
    assert len(functions) == 1
    assert functions[0].name == "fetch_data"
    assert "async" in functions[0].signature


def test_extracts_variable():
    result = parse_file("test.py", SIMPLE_CLASS)
    variables = [s for s in result.symbols if s.kind == "variable"]
    assert len(variables) == 1
    assert variables[0].name == "MAX_USERS"


def test_extracts_nested_classes():
    result = parse_file("test.py", NESTED_CLASSES)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert len(classes) == 2
    inner = [c for c in classes if c.name == "Inner"][0]
    assert inner.parent == "Outer"
    methods = [s for s in result.symbols if s.kind == "method"]
    inner_methods = [m for m in methods if m.parent == "Outer/Inner"]
    assert len(inner_methods) == 1
    assert inner_methods[0].name == "inner_method"


def test_extracts_children():
    result = parse_file("test.py", SIMPLE_CLASS)
    user = [s for s in result.symbols if s.name == "User"][0]
    assert "save" in user.children
    assert "delete" in user.children


# --- Import extraction tests ---

def test_extracts_import():
    result = parse_file("test.py", SIMPLE_FUNCTION)
    imports = result.imports
    assert len(imports) == 2
    os_import = [i for i in imports if i.module == "os"][0]
    assert os_import.names == []
    assert os_import.is_relative is False


def test_extracts_from_import():
    result = parse_file("test.py", SIMPLE_FUNCTION)
    typing_import = [i for i in result.imports if i.module == "typing"][0]
    assert "Any" in typing_import.names


def test_extracts_relative_import():
    source = "from . import utils\nfrom ..models import User\n"
    result = parse_file("test.py", source)
    rel = [i for i in result.imports if i.is_relative]
    assert len(rel) == 2


# --- Error handling tests ---

def test_syntax_error_captured():
    result = parse_file("test.py", SYNTAX_ERROR)
    assert result.error is not None
    assert result.symbols == []
    assert result.imports == []


def test_empty_file():
    result = parse_file("test.py", EMPTY_FILE)
    assert result.error is None
    assert result.symbols == []
    assert result.imports == []


# --- Signature tests ---

def test_class_signature_includes_bases():
    source = "class Dog(Animal, Serializable):\n    pass\n"
    result = parse_file("test.py", source)
    cls = result.symbols[0]
    assert "Animal" in cls.signature
    assert "Serializable" in cls.signature


def test_method_signature_includes_decorator():
    source = '''\
class Foo:
    @staticmethod
    def bar(x: int) -> int:
        return x
'''
    result = parse_file("test.py", source)
    method = [s for s in result.symbols if s.name == "bar"][0]
    assert "staticmethod" in method.decorators
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/parser.py`:

```python
import ast
from dataclasses import dataclass, field


@dataclass
class SymbolInfo:
    name: str
    kind: str  # "class", "function", "method", "variable"
    line: int
    end_line: int
    signature: str
    docstring: str | None
    parent: str | None
    children: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    line: int
    is_relative: bool


@dataclass
class ParseResult:
    symbols: list[SymbolInfo]
    imports: list[ImportInfo]
    error: str | None


def parse_file(file_path: str, source: str) -> ParseResult:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return ParseResult(symbols=[], imports=[], error=str(e))

    symbols: list[SymbolInfo] = []
    imports: list[ImportInfo] = []

    _extract_symbols(tree, symbols, parent_path=None)
    _extract_imports(tree, imports)

    return ParseResult(symbols=symbols, imports=imports, error=None)


def _extract_symbols(
    node: ast.AST,
    symbols: list[SymbolInfo],
    parent_path: str | None,
) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            info = _make_class_info(child, parent_path)
            symbols.append(info)
            child_path = f"{parent_path}/{child.name}" if parent_path else child.name
            _extract_symbols(child, symbols, parent_path=child_path)

        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info = _make_function_info(child, parent_path)
            symbols.append(info)
            # Record as child of parent
            if parent_path:
                for s in symbols:
                    if s.name == parent_path.split("/")[-1] and _path_matches(s, parent_path):
                        if child.name not in s.children:
                            s.children.append(child.name)
                        break

        elif isinstance(child, ast.Assign) and parent_path is None:
            _extract_assign(child, symbols, parent_path)

        elif isinstance(child, ast.AnnAssign) and parent_path is None:
            _extract_ann_assign(child, symbols, parent_path)

        elif isinstance(child, ast.Assign) and parent_path is not None:
            _extract_assign(child, symbols, parent_path)

        elif isinstance(child, ast.AnnAssign) and parent_path is not None:
            _extract_ann_assign(child, symbols, parent_path)


def _path_matches(symbol: SymbolInfo, parent_path: str) -> bool:
    if "/" not in parent_path:
        return symbol.parent is None and symbol.name == parent_path
    parts = parent_path.split("/")
    return symbol.name == parts[-1]


def _make_class_info(node: ast.ClassDef, parent_path: str | None) -> SymbolInfo:
    bases = [ast.unparse(b) for b in node.bases]
    base_str = f"({', '.join(bases)})" if bases else ""
    signature = f"class {node.name}{base_str}"
    decorators = [ast.unparse(d) for d in node.decorator_list]
    if decorators:
        signature = f"@{', @'.join(decorators)}\n{signature}"

    return SymbolInfo(
        name=node.name,
        kind="class",
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        signature=signature,
        docstring=_get_docstring(node),
        parent=parent_path,
        children=[],
        decorators=decorators,
    )


def _make_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent_path: str | None,
) -> SymbolInfo:
    kind = "method" if parent_path is not None else "function"
    is_async = isinstance(node, ast.AsyncFunctionDef)

    args_str = _format_args(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if is_async else "def"
    signature = f"{prefix} {node.name}({args_str}){returns}"

    decorators = [ast.unparse(d) for d in node.decorator_list]

    return SymbolInfo(
        name=node.name,
        kind=kind,
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        signature=signature,
        docstring=_get_docstring(node),
        parent=parent_path,
        children=[],
        decorators=decorators,
    )


def _format_args(args: ast.arguments) -> str:
    parts = []
    num_args = len(args.args)
    num_defaults = len(args.defaults)
    non_default_count = num_args - num_defaults

    for i, arg in enumerate(args.args):
        s = arg.arg
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        default_idx = i - non_default_count
        if default_idx >= 0:
            s += f" = {ast.unparse(args.defaults[default_idx])}"
        parts.append(s)

    if args.vararg:
        s = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            s += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(s)

    for i, arg in enumerate(args.kwonlyargs):
        s = arg.arg
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            s += f" = {ast.unparse(args.kw_defaults[i])}"
        parts.append(s)

    if args.kwarg:
        s = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            s += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(s)

    return ", ".join(parts)


def _extract_assign(
    node: ast.Assign,
    symbols: list[SymbolInfo],
    parent_path: str | None,
) -> None:
    for target in node.targets:
        if isinstance(target, ast.Name):
            symbols.append(SymbolInfo(
                name=target.id,
                kind="variable",
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=f"{target.id} = ...",
                docstring=None,
                parent=parent_path,
            ))


def _extract_ann_assign(
    node: ast.AnnAssign,
    symbols: list[SymbolInfo],
    parent_path: str | None,
) -> None:
    if isinstance(node.target, ast.Name):
        annotation = ast.unparse(node.annotation)
        symbols.append(SymbolInfo(
            name=node.target.id,
            kind="variable",
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=f"{node.target.id}: {annotation}",
            docstring=None,
            parent=parent_path,
        ))


def _get_docstring(node: ast.AST) -> str | None:
    if not hasattr(node, "body") or not node.body:
        return None
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        doc = first.value.value.strip()
        if len(doc) > 200:
            return doc[:200] + "..."
        return doc
    return None


def _extract_imports(tree: ast.Module, imports: list[ImportInfo]) -> None:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=[],
                    line=node.lineno,
                    is_relative=False,
                ))
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names] if node.names else []
            imports.append(ImportInfo(
                module=node.module or "",
                names=names,
                line=node.lineno,
                is_relative=(node.level or 0) > 0,
            ))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parser.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/parser.py tests/test_parser.py
git commit -m "feat: ast-based parser for symbol and import extraction"
```

---

### Task 5: Index Module

**Files:**
- Create: `src/ii_structure/index.py`
- Create: `tests/test_index.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index.py`:

```python
import json
import pathlib
import time
import pytest
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_index.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/index.py`:

```python
import hashlib
import json
import pathlib
from dataclasses import asdict

import pathspec

from ii_structure.parser import parse_file

INDEX_VERSION = 1
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules", ".ii-structure", ".pytest_cache"}


class Index:
    def __init__(
        self,
        project_root: str,
        files: dict,
        version: int = INDEX_VERSION,
    ):
        self.project_root = project_root
        self.files = files
        self.version = version

    @classmethod
    def build(cls, root: pathlib.Path) -> "Index":
        root = root.resolve()
        gitignore_spec = _load_gitignore(root)
        files = {}
        for py_file in _walk_python_files(root, gitignore_spec):
            rel = str(py_file.relative_to(root))
            entry = _parse_and_build_entry(py_file)
            files[rel] = entry
        return cls(project_root=str(root), files=files)

    def save(self, state_dir: pathlib.Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.version,
            "project_root": self.project_root,
            "files": self.files,
        }
        index_path = state_dir / "index.json"
        index_path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, state_dir: pathlib.Path) -> "Index":
        index_path = state_dir / "index.json"
        data = json.loads(index_path.read_text())
        return cls(
            project_root=data["project_root"],
            files=data["files"],
            version=data.get("version", INDEX_VERSION),
        )

    def refresh(self, root: pathlib.Path) -> None:
        root = root.resolve()
        gitignore_spec = _load_gitignore(root)
        current_files = set()

        for py_file in _walk_python_files(root, gitignore_spec):
            rel = str(py_file.relative_to(root))
            current_files.add(rel)
            if rel in self.files:
                stored_mtime = self.files[rel].get("mtime", 0)
                actual_mtime = py_file.stat().st_mtime
                if actual_mtime != stored_mtime:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                    actual_hash = _content_hash(content)
                    if actual_hash != self.files[rel].get("content_hash"):
                        self.files[rel] = _parse_and_build_entry(py_file)
                    else:
                        self.files[rel]["mtime"] = actual_mtime
            else:
                self.files[rel] = _parse_and_build_entry(py_file)

        stale_keys = set(self.files.keys()) - current_files
        for key in stale_keys:
            del self.files[key]

    def get_symbols(self, rel_path: str) -> list[dict]:
        if rel_path in self.files:
            return self.files[rel_path]["symbols"]
        return []

    def search_symbols(self, name_path: str) -> list[dict]:
        results = []
        parts = name_path.strip("/").split("/")

        for rel_path, file_data in self.files.items():
            for symbol in file_data["symbols"]:
                if len(parts) == 1:
                    if symbol["name"] == parts[0]:
                        results.append({**symbol, "file": rel_path})
                elif len(parts) == 2:
                    if symbol["name"] == parts[-1] and symbol.get("parent") == parts[0]:
                        results.append({**symbol, "file": rel_path})
                else:
                    full_path = symbol["name"]
                    if symbol.get("parent"):
                        full_path = f"{symbol['parent']}/{symbol['name']}"
                    if full_path == name_path.strip("/"):
                        results.append({**symbol, "file": rel_path})

        return results

    def all_symbols(self) -> list[dict]:
        results = []
        for rel_path, file_data in self.files.items():
            for symbol in file_data["symbols"]:
                results.append({**symbol, "file": rel_path})
        return results


def load_or_build_index(root: pathlib.Path) -> Index:
    state_dir = root / ".ii-structure"
    index_path = state_dir / "index.json"

    if index_path.exists():
        try:
            idx = Index.load(state_dir)
            idx.refresh(root)
            idx.save(state_dir)
            return idx
        except (json.JSONDecodeError, KeyError):
            pass

    idx = Index.build(root)
    idx.save(state_dir)
    return idx


def _parse_and_build_entry(py_file: pathlib.Path) -> dict:
    content = py_file.read_text(encoding="utf-8", errors="replace")
    result = parse_file(str(py_file), content)
    return {
        "mtime": py_file.stat().st_mtime,
        "content_hash": _content_hash(content),
        "symbols": [asdict(s) for s in result.symbols],
        "imports": [asdict(i) for i in result.imports],
        "parse_error": result.error,
    }


def _content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _load_gitignore(root: pathlib.Path) -> pathspec.PathSpec | None:
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        patterns = gitignore_path.read_text().splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    return None


def _walk_python_files(
    root: pathlib.Path,
    gitignore_spec: pathspec.PathSpec | None,
) -> list[pathlib.Path]:
    files = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        parts = rel.parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if gitignore_spec and gitignore_spec.match_file(str(rel)):
            continue
        files.append(path)
    return sorted(files)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_index.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/index.py tests/test_index.py
git commit -m "feat: structural index with build, save, load, refresh"
```

---

### Task 6: Outline Command

**Files:**
- Create: `src/ii_structure/commands/__init__.py`
- Create: `src/ii_structure/commands/outline.py`
- Create: `tests/test_commands/test_outline.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_commands/__init__.py` (empty file).

Create `tests/test_commands/test_outline.py`:

```python
import pytest
from ii_structure.index import Index
from ii_structure.commands.outline import execute


def test_outline_returns_all_symbols(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py")
    symbols = result["symbols"]
    names = {s["name"] for s in symbols}
    assert "User" in names
    assert "Product" in names
    assert "MAX_USERS" in names


def test_outline_top_depth(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py", depth="top")
    symbols = result["symbols"]
    # top-level only: User, Product, MAX_USERS — no methods
    assert all(s.get("parent") is None for s in symbols)


def test_outline_full_depth(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py", depth="full")
    symbols = result["symbols"]
    names = {s["name"] for s in symbols}
    assert "save" in names
    assert "delete" in names


def test_outline_kind_filter(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py", kind="class")
    symbols = result["symbols"]
    assert all(s["kind"] == "class" for s in symbols)
    assert len(symbols) == 2


def test_outline_includes_imports(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="views.py")
    assert "imports" in result
    modules = {i["module"] for i in result["imports"]}
    assert "models" in modules


def test_outline_file_not_found(simple_project):
    idx = Index.build(simple_project)
    with pytest.raises(FileNotFoundError):
        execute(idx, file="nonexistent.py")


def test_outline_includes_file_path(simple_project):
    idx = Index.build(simple_project)
    result = execute(idx, file="models.py")
    assert result["file"] == "models.py"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands/test_outline.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/commands/__init__.py` (empty file).

Create `src/ii_structure/commands/outline.py`:

```python
from ii_structure.index import Index


def execute(
    idx: Index,
    file: str,
    depth: str = "top",
    kind: str | None = None,
) -> dict:
    if file not in idx.files:
        raise FileNotFoundError(f"File '{file}' not found in index")

    file_data = idx.files[file]
    symbols = file_data["symbols"]

    if depth == "top":
        symbols = [s for s in symbols if s.get("parent") is None]

    if kind is not None:
        symbols = [s for s in symbols if s["kind"] == kind]

    # Build clean output — strip internal fields
    clean_symbols = []
    for s in symbols:
        entry = {
            "name": s["name"],
            "kind": s["kind"],
            "line": s["line"],
            "signature": s["signature"],
        }
        if s.get("docstring"):
            entry["docstring"] = s["docstring"]
        if s.get("children"):
            entry["children"] = s["children"]
        if s.get("decorators"):
            entry["decorators"] = s["decorators"]
        clean_symbols.append(entry)

    return {
        "file": file,
        "symbols": clean_symbols,
        "imports": file_data["imports"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_commands/test_outline.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/commands/ tests/test_commands/
git commit -m "feat: outline command — file skeleton with depth and kind filters"
```

---

### Task 7: Locate Command

**Files:**
- Create: `src/ii_structure/commands/locate.py`
- Create: `tests/test_commands/test_locate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_commands/test_locate.py`:

```python
import pytest
from ii_structure.index import Index
from ii_structure.commands.locate import execute


def test_locate_by_name(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User")
    assert len(results) == 1
    assert results[0]["name"] == "User"
    assert results[0]["kind"] == "class"
    assert results[0]["file"] == "models.py"


def test_locate_by_name_path(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User/save")
    assert len(results) == 1
    assert results[0]["name"] == "save"
    assert results[0]["kind"] == "method"


def test_locate_returns_multiple(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="save")
    # User.save and Product.save
    assert len(results) == 2


def test_locate_with_kind_filter(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User", kind="class")
    assert len(results) == 1
    assert results[0]["kind"] == "class"


def test_locate_with_file_filter(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="save", file="models.py")
    assert all(r["file"] == "models.py" for r in results)


def test_locate_anchored(simple_project):
    idx = Index.build(simple_project)
    # /User means top-level only
    results = execute(idx, name="/User")
    assert len(results) == 1
    assert results[0]["parent"] is None


def test_locate_substring(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="load", match="substring")
    assert any(r["name"] == "load_config" for r in results)


def test_locate_not_found(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="NonExistent")
    assert results == []


def test_locate_result_shape(simple_project):
    idx = Index.build(simple_project)
    results = execute(idx, name="User")
    r = results[0]
    assert "file" in r
    assert "line" in r
    assert "kind" in r
    assert "name" in r
    assert "signature" in r
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands/test_locate.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/commands/locate.py`:

```python
from ii_structure.index import Index


def execute(
    idx: Index,
    name: str,
    kind: str | None = None,
    file: str | None = None,
    match: str = "exact",
) -> list[dict]:
    anchored = name.startswith("/")
    clean_name = name.lstrip("/")
    parts = clean_name.split("/")

    results = []

    for rel_path, file_data in idx.files.items():
        if file is not None and rel_path != file:
            continue

        for symbol in file_data["symbols"]:
            if not _matches(symbol, parts, match, anchored):
                continue
            if kind is not None and symbol["kind"] != kind:
                continue

            results.append({
                "file": rel_path,
                "line": symbol["line"],
                "kind": symbol["kind"],
                "name": symbol["name"],
                "signature": symbol["signature"],
                "docstring": symbol.get("docstring"),
                "parent": symbol.get("parent"),
            })

    return results


def _matches(
    symbol: dict,
    parts: list[str],
    match: str,
    anchored: bool,
) -> bool:
    if len(parts) == 1:
        target = parts[0]
        if anchored and symbol.get("parent") is not None:
            return False
        if match == "substring":
            return target.lower() in symbol["name"].lower()
        return symbol["name"] == target

    # Name path: e.g. ["User", "save"]
    if symbol["name"] != parts[-1]:
        return False
    if symbol.get("parent") is None:
        return False

    parent_parts = symbol["parent"].split("/")
    expected_parents = parts[:-1]

    if anchored:
        return parent_parts == expected_parents
    # Non-anchored: expected parents must be a suffix of actual parents
    if len(expected_parents) > len(parent_parts):
        return False
    return parent_parts[-len(expected_parents):] == expected_parents
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_commands/test_locate.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/commands/locate.py tests/test_commands/test_locate.py
git commit -m "feat: locate command — find symbol definitions by name path"
```

---

### Task 8: CLI Wiring

**Files:**
- Create: `src/ii_structure/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import json
import yaml
import subprocess
import pathlib
import pytest


def run_cli(*args, cwd=None):
    result = subprocess.run(
        ["python", "-m", "ii_structure.cli", *args],
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
    assert (project_with_root / ".ii-structure" / "index.json").exists()

    # Second run with --no-cache rebuilds
    result = run_cli("--no-cache", "locate", "User", cwd=project_with_root)
    parsed = yaml.safe_load(result.stdout)
    assert parsed["ok"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/cli.py`:

```python
import pathlib
import sys

import click

from ii_structure.root import find_project_root
from ii_structure.index import Index, load_or_build_index
from ii_structure.output import format_success, format_error


@click.group()
@click.option("--project", type=click.Path(exists=True), default=None, help="Override project root detection")
@click.option("--no-cache", is_flag=True, default=False, help="Rebuild index from scratch")
@click.pass_context
def cli(ctx, project, no_cache):
    ctx.ensure_object(dict)
    try:
        if project:
            root = pathlib.Path(project).resolve()
        else:
            root = find_project_root(pathlib.Path.cwd())
        ctx.obj["root"] = root
        ctx.obj["no_cache"] = no_cache
    except FileNotFoundError as e:
        click.echo(format_error("init", str(e), suggestion="Use --project to specify the root."))
        ctx.exit(1)


def _get_index(ctx) -> Index:
    root = ctx.obj["root"]
    if ctx.obj["no_cache"]:
        idx = Index.build(root)
        state_dir = root / ".ii-structure"
        idx.save(state_dir)
        return idx
    return load_or_build_index(root)


@cli.command()
@click.argument("file")
@click.option("--depth", type=click.Choice(["top", "full"]), default="top")
@click.option("--kind", type=click.Choice(["class", "function", "method", "variable", "import"]), default=None)
@click.pass_context
def outline(ctx, file, depth, kind):
    """File skeleton: classes, functions, signatures, docstrings."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.outline import execute
        result = execute(idx, file=file, depth=depth, kind=kind)
        click.echo(format_success("outline", result))
    except FileNotFoundError as e:
        click.echo(format_error("outline", str(e)))
        ctx.exit(1)
    except Exception as e:
        click.echo(format_error("outline", str(e)))
        sys.exit(1)


@cli.command()
@click.argument("name")
@click.option("--kind", type=click.Choice(["class", "function", "method", "variable"]), default=None)
@click.option("--file", default=None, help="Restrict to a specific file")
@click.option("--match", type=click.Choice(["exact", "substring"]), default="exact")
@click.pass_context
def locate(ctx, name, kind, file, match):
    """Find where a symbol is defined by name path."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.locate import execute
        results = execute(idx, name=name, kind=kind, file=file, match=match)
        click.echo(format_success("locate", results))
    except Exception as e:
        click.echo(format_error("locate", str(e)))
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cli.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Verify CLI works end-to-end**

```bash
cd /Users/somen/Projects/ii-structure
ii-structure --project tests/fixtures/simple_project outline models.py
ii-structure --project tests/fixtures/simple_project locate User
ii-structure --project tests/fixtures/simple_project locate User/save
```

Expected: YAML output for each command.

- [ ] **Step 6: Commit**

```bash
git add src/ii_structure/cli.py tests/test_cli.py
git commit -m "feat: CLI wiring — outline and locate commands end-to-end"
```

---

### Task 9: Full Test Suite Run and Cleanup

**Files:**
- No new files — verification only

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/somen/Projects/ii-structure
pytest tests/ -v --tb=short
```

Expected: all tests pass (6 output + 6 root + 16 parser + 14 index + 7 outline + 9 locate + 9 CLI = ~67 tests).

- [ ] **Step 2: Run with coverage**

```bash
pytest tests/ --cov=ii_structure --cov-report=term-missing
```

Expected: >80% coverage across all modules.

- [ ] **Step 3: Fix any failures or gaps**

If any tests fail, fix the issue and re-run. If coverage is below 80% on any module, add tests for uncovered paths.

- [ ] **Step 4: Test the CLI manually against itself**

```bash
cd /Users/somen/Projects/ii-structure
ii-structure outline src/ii_structure/parser.py --depth full
ii-structure locate parse_file
ii-structure locate SymbolInfo
ii-structure locate Index/build
```

Expected: the tool can navigate its own codebase.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: test suite cleanup and coverage gaps"
```

(Only if there were fixes needed.)
