# Multi-Language Support: Go + TypeScript

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Go and TypeScript support at the same quality level as Python. All 7 commands + help work identically across all three languages. `usages` uses language servers (gopls/tsserver) when available, degrades gracefully when not.

**Architecture:** Extract current Python code into a backend, add Go and TypeScript backends using tree-sitter for parsing and LSP for type-resolved usages. A generic LSP client is shared by Go and TS. The index routes to the correct backend by file extension.

**Tech Stack:** tree-sitter-language-pack (new dep), python-lsp-jsonrpc (new dep for LSP client), existing stack.

---

## File Map

```
src/ii_structure/
├── backends/
│   ├── __init__.py         # get_backend(extension) dispatcher
│   ├── base.py             # LanguageBackend protocol + shared helpers
│   ├── python.py           # ast + Jedi (extracted from parser.py + resolver.py)
│   ├── golang.py           # tree-sitter walker + optional gopls
│   └── typescript.py       # tree-sitter walker + optional tsserver
├── lsp_client.py           # Generic LSP subprocess client (shared by Go/TS)
├── parser.py               # KEPT — re-exports from backends.python for backward compat
├── resolver.py             # KEPT — re-exports from backends.python for backward compat
├── index.py                # MODIFIED — route by extension, walk all supported files
├── root.py                 # MODIFIED — add go.mod, tsconfig.json, package.json markers
├── cli.py                  # MODIFIED — init detects language servers
├── ... (commands unchanged)

tests/
├── fixtures/
│   ├── simple_project/      # existing Python fixture
│   ├── jedi_project/        # existing Python fixture
│   ├── go_project/          # NEW — small Go project
│   └── ts_project/          # NEW — small TypeScript project
├── test_backends/
│   ├── test_python.py       # existing parser tests, re-pointed
│   ├── test_golang.py       # NEW
│   └── test_typescript.py   # NEW
├── test_lsp_client.py       # NEW
```

---

## Phase 5: Backend Abstraction (refactor only — zero behavior change)

### Task 1: Create backend protocol and extract Python backend

**Files:**
- Create: `src/ii_structure/backends/__init__.py`
- Create: `src/ii_structure/backends/base.py`
- Create: `src/ii_structure/backends/python.py`
- Modify: `src/ii_structure/parser.py` (thin re-export wrapper)
- Modify: `src/ii_structure/resolver.py` (thin re-export wrapper)
- Modify: `src/ii_structure/index.py` (use backend dispatcher)

- [ ] **Step 1: Create `src/ii_structure/backends/base.py`**

```python
from __future__ import annotations
from typing import Protocol
from ii_structure.parser import SymbolInfo, ImportInfo, ParseResult


LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
}


class LanguageBackend(Protocol):
    """Interface that every language backend must implement."""

    def parse_file(self, file_path: str, source: str) -> ParseResult:
        """Parse source and extract symbols + imports."""
        ...

    def find_usages(
        self,
        project_root: str,
        name: str,
        index,  # Index type — avoid circular import
        path_scope: str | None = None,
        kind_filter: str | None = None,
        limit: int = 50,
        include_tests: bool = True,
    ) -> list[dict]:
        """Find all references to a symbol."""
        ...

    def get_definition_source(
        self,
        project_root: str,
        name: str,
        index,
        file_hint: str | None = None,
    ) -> dict | None:
        """Get the full source body of a symbol."""
        ...
```

- [ ] **Step 2: Create `src/ii_structure/backends/__init__.py`**

```python
from __future__ import annotations
import pathlib
from ii_structure.backends.base import LanguageBackend, LANGUAGE_EXTENSIONS


_backends: dict[str, LanguageBackend] = {}


def get_backend(file_path: str) -> LanguageBackend:
    """Get the appropriate backend for a file based on its extension."""
    ext = pathlib.Path(file_path).suffix
    lang = LANGUAGE_EXTENSIONS.get(ext)

    if lang is None:
        raise ValueError(f"Unsupported file type: {ext}")

    if lang not in _backends:
        if lang == "python":
            from ii_structure.backends.python import PythonBackend
            _backends[lang] = PythonBackend()
        elif lang == "go":
            from ii_structure.backends.golang import GoBackend
            _backends[lang] = GoBackend()
        elif lang == "typescript":
            from ii_structure.backends.typescript import TypeScriptBackend
            _backends[lang] = TypeScriptBackend()

    return _backends[lang]


def get_language(file_path: str) -> str | None:
    """Return the language name for a file, or None if unsupported."""
    ext = pathlib.Path(file_path).suffix
    return LANGUAGE_EXTENSIONS.get(ext)


def supported_extensions() -> set[str]:
    """Return all supported file extensions."""
    return set(LANGUAGE_EXTENSIONS.keys())
```

- [ ] **Step 3: Create `src/ii_structure/backends/python.py`**

Move all logic from `parser.py` and `resolver.py` into a `PythonBackend` class. The class wraps the existing functions:

```python
from ii_structure.parser import parse_file as _parse_file, SymbolInfo, ImportInfo, ParseResult
from ii_structure.resolver import (
    find_usages as _find_usages,
    get_definition_source as _get_definition_source,
)


class PythonBackend:
    def parse_file(self, file_path: str, source: str) -> ParseResult:
        return _parse_file(file_path, source)

    def find_usages(self, project_root, name, index, path_scope=None, kind_filter=None, limit=50, include_tests=True):
        return _find_usages(project_root, name, index, path_scope, kind_filter, limit, include_tests)

    def get_definition_source(self, project_root, name, index, file_hint=None):
        return _get_definition_source(project_root, name, index, file_hint)
```

This is a thin wrapper — `parser.py` and `resolver.py` keep their code and stay importable for backward compatibility. No code moves, no risk.

- [ ] **Step 4: Modify `index.py` — route by extension**

Change `_walk_python_files` to `_walk_source_files` — glob for all supported extensions.
Change `_parse_and_build_entry` to detect language and use the correct backend.

Key changes:
- `root.rglob("*.py")` → iterate over all `supported_extensions()`
- `from ii_structure.parser import parse_file` → `from ii_structure.backends import get_backend`
- `parse_file(str(py_file), content)` → `get_backend(str(py_file)).parse_file(str(py_file), content)`

- [ ] **Step 5: Modify `resolver.py` and command modules — route usages/body through backend**

Update `commands/usages.py` and `commands/body.py` to detect the language of the target symbol's file and use the correct backend:

```python
# In commands/usages.py
from ii_structure.backends import get_backend

def execute(idx, project_root, name, ...):
    # Find the symbol first to know which file/language
    candidates = idx.search_symbols(name)
    if not candidates:
        return []
    # Use the backend for the first candidate's file
    backend = get_backend(candidates[0]["file"])
    return backend.find_usages(project_root, name, idx, ...)
```

- [ ] **Step 6: Modify `root.py` — add Go and TS markers**

Add `"go.mod"`, `"tsconfig.json"`, `"package.json"` to `MARKERS`:

```python
MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "go.mod", "tsconfig.json", "package.json", ".git")
```

- [ ] **Step 7: Run ALL existing tests — nothing should break**

```bash
pytest tests/ -v --tb=short
```

Expected: all 137 tests pass. This is a refactor — zero behavior change.

- [ ] **Step 8: Commit**

```bash
git add src/ii_structure/backends/ src/ii_structure/index.py src/ii_structure/root.py src/ii_structure/commands/usages.py src/ii_structure/commands/body.py
git commit -m "refactor: extract LanguageBackend protocol, route by file extension

Python behavior unchanged. Backends dispatcher routes .py to PythonBackend.
Prepares for Go and TypeScript support."
```

---

## Phase 6: Go Support

### Task 2: Add tree-sitter-language-pack dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency**

```toml
dependencies = [
    "click>=8.0",
    "pyyaml>=6.0",
    "pathspec>=0.11",
    "jedi>=0.19",
    "tree-sitter-language-pack>=1.0",
]
```

- [ ] **Step 2: Reinstall and verify**

```bash
pip install -e ".[dev]"
python -c "from tree_sitter_language_pack import get_parser; p = get_parser('go'); print('Go parser OK')"
python -c "from tree_sitter_language_pack import get_parser; p = get_parser('typescript'); print('TS parser OK')"
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add tree-sitter-language-pack dependency for Go and TypeScript parsing"
```

---

### Task 3: Go test fixtures

**Files:**
- Create: `tests/fixtures/go_project/go.mod`
- Create: `tests/fixtures/go_project/main.go`
- Create: `tests/fixtures/go_project/server/server.go`
- Create: `tests/fixtures/go_project/server/handler.go`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/go_project/go.mod`:
```
module example.com/myapp

go 1.21
```

Create `tests/fixtures/go_project/main.go`:
```go
// Package main is the entry point for the application.
package main

import (
	"fmt"
	"example.com/myapp/server"
)

// Version is the application version.
var Version = "1.0.0"

// MaxRetries is the maximum number of retries.
const MaxRetries = 3

func main() {
	srv := server.NewServer(":8080")
	fmt.Println("Starting server on", srv.Addr)
	srv.Start()
}
```

Create `tests/fixtures/go_project/server/server.go`:
```go
// Package server provides HTTP server functionality.
package server

import "net/http"

// Server handles HTTP requests.
type Server struct {
	Addr   string
	mux    *http.ServeMux
}

// Config holds server configuration.
type Config struct {
	Addr    string
	Timeout int
}

// Handler defines the interface for request handlers.
type Handler interface {
	ServeHTTP(w http.ResponseWriter, r *http.Request)
	Health() bool
}

// NewServer creates a new server instance.
func NewServer(addr string) *Server {
	return &Server{
		Addr: addr,
		mux:  http.NewServeMux(),
	}
}

// Start begins listening for requests.
func (s *Server) Start() error {
	s.mux.HandleFunc("/health", handleHealth)
	return http.ListenAndServe(s.Addr, s.mux)
}

// Stop gracefully shuts down the server.
func (s *Server) Stop() error {
	return nil
}
```

Create `tests/fixtures/go_project/server/handler.go`:
```go
package server

import (
	"fmt"
	"net/http"
)

func handleHealth(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "ok")
}

// ProcessRequest validates and processes an incoming request.
func ProcessRequest(w http.ResponseWriter, r *http.Request) error {
	if r.Method != http.MethodPost {
		return fmt.Errorf("invalid method: %s", r.Method)
	}
	return nil
}
```

- [ ] **Step 2: Add fixture to conftest.py**

```python
@pytest.fixture
def go_project(fixtures_dir):
    return fixtures_dir / "go_project"
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/go_project/ tests/conftest.py
git commit -m "feat: add Go test fixture project"
```

---

### Task 4: Go backend — tree-sitter parser

**Files:**
- Create: `src/ii_structure/backends/golang.py`
- Create: `tests/test_backends/test_golang.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_backends/__init__.py` (empty).

Create `tests/test_backends/test_golang.py`:

```python
import pytest
from ii_structure.backends.golang import GoBackend
from ii_structure.parser import ParseResult

backend = GoBackend()

SIMPLE_GO = '''\
// Package main is the entry point.
package main

import (
	"fmt"
	"net/http"
)

// Version is the app version.
var Version = "1.0.0"

// MaxRetries controls retry behavior.
const MaxRetries = 3

// Server handles HTTP requests.
type Server struct {
	Addr string
	mux  *http.ServeMux
}

// Handler is the interface for handlers.
type Handler interface {
	ServeHTTP(w http.ResponseWriter, r *http.Request)
}

// NewServer creates a new server.
func NewServer(addr string) *Server {
	return &Server{Addr: addr}
}

// Start begins listening.
func (s *Server) Start() error {
	return http.ListenAndServe(s.Addr, s.mux)
}
'''

def test_extracts_function():
    result = backend.parse_file("main.go", SIMPLE_GO)
    assert result.error is None
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "NewServer" for f in funcs)
    ns = [f for f in funcs if f.name == "NewServer"][0]
    assert "addr string" in ns.signature
    assert "*Server" in ns.signature

def test_extracts_method():
    result = backend.parse_file("main.go", SIMPLE_GO)
    methods = [s for s in result.symbols if s.kind == "method"]
    assert any(m.name == "Start" for m in methods)
    start = [m for m in methods if m.name == "Start"][0]
    assert start.parent == "Server"

def test_extracts_struct():
    result = backend.parse_file("main.go", SIMPLE_GO)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert any(c.name == "Server" for c in classes)

def test_extracts_interface():
    result = backend.parse_file("main.go", SIMPLE_GO)
    ifaces = [s for s in result.symbols if s.kind == "interface"]
    assert any(i.name == "Handler" for i in ifaces)

def test_extracts_variable():
    result = backend.parse_file("main.go", SIMPLE_GO)
    vars_ = [s for s in result.symbols if s.kind == "variable"]
    names = {v.name for v in vars_}
    assert "Version" in names
    assert "MaxRetries" in names

def test_extracts_imports():
    result = backend.parse_file("main.go", SIMPLE_GO)
    modules = {i.module for i in result.imports}
    assert "fmt" in modules
    assert "net/http" in modules

def test_extracts_docstring():
    result = backend.parse_file("main.go", SIMPLE_GO)
    server = [s for s in result.symbols if s.name == "Server" and s.kind == "class"][0]
    assert server.docstring is not None
    assert "HTTP" in server.docstring

def test_extracts_children():
    result = backend.parse_file("main.go", SIMPLE_GO)
    server = [s for s in result.symbols if s.name == "Server" and s.kind == "class"][0]
    assert "Start" in server.children

def test_empty_file():
    result = backend.parse_file("empty.go", "")
    assert result.error is None
    assert result.symbols == []

def test_syntax_error():
    result = backend.parse_file("bad.go", "func broken(")
    assert result.error is not None

def test_method_signature():
    result = backend.parse_file("main.go", SIMPLE_GO)
    start = [s for s in result.symbols if s.name == "Start"][0]
    assert "func" in start.signature
    assert "error" in start.signature
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_backends/test_golang.py -v
```

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/backends/golang.py`:

The Go backend walks the tree-sitter parse tree extracting symbols. Key node types:
- `function_declaration` → kind=function
- `method_declaration` → kind=method (receiver type = parent)
- `type_spec` with `struct_type` child → kind=class
- `type_spec` with `interface_type` child → kind=interface
- `var_spec` / `const_spec` → kind=variable
- `import_spec` → ImportInfo
- `comment` preceding a declaration → docstring

The implementation should:
1. Parse with `tree_sitter_language_pack.get_parser("go")`
2. Walk root node children recursively
3. For each recognized node type, extract name, line, end_line, signature, docstring, parent
4. Return `ParseResult` with the same dataclasses as Python

For `find_usages` and `get_definition_source`: stub them to raise NotImplementedError initially. We'll implement LSP in Task 6.

Signature format:
- Functions: `func NewServer(addr string) *Server`
- Methods: `func (s *Server) Start() error`
- Structs: `type Server struct`
- Interfaces: `type Handler interface`

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_backends/test_golang.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/backends/golang.py tests/test_backends/
git commit -m "feat: Go backend — tree-sitter parser for structs, functions, methods, interfaces"
```

---

### Task 5: Integrate Go into index and verify commands work

**Files:**
- Modify: `src/ii_structure/index.py` (if not done in Task 1)
- Create: `tests/test_go_integration.py`

- [ ] **Step 1: Write integration tests**

```python
import pytest
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
    result = execute(idx, file="main.go")
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
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_go_integration.py -v
```

- [ ] **Step 3: Fix any issues and commit**

```bash
git add tests/test_go_integration.py src/ii_structure/
git commit -m "feat: Go fully integrated — all structural commands work for .go files"
```

---

## Phase 7: TypeScript Support

### Task 6: TypeScript test fixtures

**Files:**
- Create: `tests/fixtures/ts_project/tsconfig.json`
- Create: `tests/fixtures/ts_project/src/models.ts`
- Create: `tests/fixtures/ts_project/src/services.ts`
- Create: `tests/fixtures/ts_project/src/utils.ts`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/ts_project/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "strict": true
  }
}
```

Create `tests/fixtures/ts_project/src/models.ts`:
```typescript
/** A user in the system. */
export interface User {
  id: number;
  name: string;
  email: string;
}

/** A product listing. */
export interface Product {
  id: number;
  title: string;
  price: number;
}

/** Base class for all services. */
export class BaseService {
  protected db: any;

  constructor(db: any) {
    this.db = db;
  }

  /** Log a message. */
  log(message: string): void {
    console.log(message);
  }
}

/** Maximum number of items per page. */
export const MAX_PAGE_SIZE = 100;

/** Format a user for display. */
export function formatUser(user: User): string {
  return `${user.name} <${user.email}>`;
}

export type UserRole = "admin" | "user" | "guest";
```

Create `tests/fixtures/ts_project/src/services.ts`:
```typescript
import { User, Product, BaseService } from "./models";

/** Manages user operations. */
export class UserService extends BaseService {
  /** Create a new user. */
  async createUser(name: string, email: string): Promise<User> {
    this.log(`Creating user: ${name}`);
    return { id: 1, name, email };
  }

  /** Delete a user by ID. */
  async deleteUser(id: number): Promise<boolean> {
    return true;
  }
}

/** Fetch a user by ID. */
export const getUser = async (id: number): Promise<User | null> => {
  return null;
};

/** Create a product. */
export const createProduct = (title: string, price: number): Product => {
  return { id: 1, title, price };
};
```

Create `tests/fixtures/ts_project/src/utils.ts`:
```typescript
import { User } from "./models";

/** Validate an email address. */
export function validateEmail(email: string): boolean {
  return email.includes("@");
}

/** Get user initials. */
export function getUserInitials(user: User): string {
  return user.name.split(" ").map(n => n[0]).join("");
}

export default validateEmail;
```

- [ ] **Step 2: Add fixture to conftest.py**

```python
@pytest.fixture
def ts_project(fixtures_dir):
    return fixtures_dir / "ts_project"
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/ts_project/ tests/conftest.py
git commit -m "feat: add TypeScript test fixture project"
```

---

### Task 7: TypeScript backend — tree-sitter parser

**Files:**
- Create: `src/ii_structure/backends/typescript.py`
- Create: `tests/test_backends/test_typescript.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_backends/test_typescript.py`:

```python
import pytest
from ii_structure.backends.typescript import TypeScriptBackend
from ii_structure.parser import ParseResult

backend = TypeScriptBackend()

SIMPLE_TS = '''\
import { User } from "./models";

/** Maximum page size. */
export const MAX_PAGE_SIZE = 100;

/** A user in the system. */
export interface UserProfile {
  id: number;
  name: string;
}

/** Base class for services. */
export class BaseService {
  protected db: any;

  constructor(db: any) {
    this.db = db;
  }

  /** Log a message. */
  log(message: string): void {
    console.log(message);
  }
}

/** Format a user for display. */
export function formatUser(user: User): string {
  return `${user.name}`;
}

/** Fetch a user by ID. */
export const getUser = async (id: number): Promise<User | null> => {
  return null;
};

export type UserRole = "admin" | "user";
'''

def test_extracts_function():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    assert result.error is None
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "formatUser" for f in funcs)

def test_extracts_arrow_function():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "getUser" for f in funcs)

def test_extracts_class():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert any(c.name == "BaseService" for c in classes)

def test_extracts_interface():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    ifaces = [s for s in result.symbols if s.kind == "interface"]
    assert any(i.name == "UserProfile" for i in ifaces)

def test_extracts_type_alias():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    types = [s for s in result.symbols if s.kind == "type"]
    assert any(t.name == "UserRole" for t in types)

def test_extracts_variable():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    vars_ = [s for s in result.symbols if s.kind == "variable"]
    assert any(v.name == "MAX_PAGE_SIZE" for v in vars_)

def test_extracts_method():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    methods = [s for s in result.symbols if s.kind == "method"]
    assert any(m.name == "log" for m in methods)
    log = [m for m in methods if m.name == "log"][0]
    assert log.parent == "BaseService"

def test_extracts_imports():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    assert len(result.imports) >= 1
    assert any(i.module == "./models" for i in result.imports)
    assert "User" in result.imports[0].names

def test_extracts_docstring():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    base = [s for s in result.symbols if s.name == "BaseService"][0]
    assert base.docstring is not None
    assert "Base class" in base.docstring

def test_extracts_children():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    base = [s for s in result.symbols if s.name == "BaseService"][0]
    assert "log" in base.children

def test_empty_file():
    result = backend.parse_file("empty.ts", "")
    assert result.error is None
    assert result.symbols == []

def test_tsx_support():
    tsx = 'export const App = () => { return <div>Hello</div>; };'
    result = backend.parse_file("app.tsx", tsx)
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "App" for f in funcs)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write the implementation**

Create `src/ii_structure/backends/typescript.py`:

Walk the tree-sitter tree. Key node types:
- `function_declaration` → kind=function
- `lexical_declaration` containing `variable_declarator` with `arrow_function` value → kind=function (name from the variable)
- `class_declaration` → kind=class
- `method_definition` inside class body → kind=method
- `interface_declaration` → kind=interface
- `type_alias_declaration` → kind=type
- `lexical_declaration` with non-function value (const/let) → kind=variable
- `import_statement` → ImportInfo (parse `named_imports` for names, `string` for module path)
- `comment` with `/**` prefix preceding a declaration → docstring (JSDoc)
- `export_statement` wrapping any of the above → same kind, flagged

Use `get_parser("typescript")` for `.ts` files and `get_parser("tsx")` for `.tsx` files.

Signature format:
- Functions: `function formatUser(user: User): string`
- Arrow functions: `const getUser = async (id: number): Promise<User | null>`
- Classes: `class BaseService`
- Interfaces: `interface UserProfile`
- Types: `type UserRole = "admin" | "user"`

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/backends/typescript.py tests/test_backends/test_typescript.py
git commit -m "feat: TypeScript backend — tree-sitter parser for classes, functions, arrow functions, interfaces, types"
```

---

### Task 8: Integrate TypeScript into index and verify commands work

**Files:**
- Create: `tests/test_ts_integration.py`

Same pattern as Task 5 but for TypeScript. Tests: index builds, outline works, locate works, body works, search works, files --summary works, imports works, mixed project with .py + .ts + .go.

- [ ] **Step 1: Write integration tests**
- [ ] **Step 2: Run and fix**
- [ ] **Step 3: Commit**

```bash
git add tests/test_ts_integration.py
git commit -m "feat: TypeScript fully integrated — all structural commands work for .ts/.tsx files"
```

---

## Phase 8: LSP Client for Type-Resolved Usages

### Task 9: Generic LSP client

**Files:**
- Create: `src/ii_structure/lsp_client.py`
- Create: `tests/test_lsp_client.py`

- [ ] **Step 1: Write the LSP client**

A minimal LSP client that:
1. Spawns a language server subprocess
2. Sends `initialize` with project root
3. Opens a document (`textDocument/didOpen`)
4. Requests references (`textDocument/references`)
5. Shuts down cleanly

~100 lines. Uses JSON-RPC over stdio. No external LSP library needed — the protocol is simple:

```python
class LspClient:
    def __init__(self, command: list[str], project_root: str):
        """Spawn language server subprocess."""

    def is_available(self) -> bool:
        """Check if the server binary exists on PATH."""

    def find_references(self, file: str, line: int, column: int) -> list[dict]:
        """Find all references to symbol at position. Returns [{file, line, column}]."""

    def shutdown(self):
        """Cleanly shut down the server."""
```

- [ ] **Step 2: Test with a mock — don't require gopls/tsserver in CI**

Test the JSON-RPC encoding/decoding, the message framing (Content-Length header), and the client lifecycle with a fake subprocess.

- [ ] **Step 3: Commit**

```bash
git add src/ii_structure/lsp_client.py tests/test_lsp_client.py
git commit -m "feat: generic LSP client for language server integration"
```

---

### Task 10: Wire LSP into Go and TypeScript backends

**Files:**
- Modify: `src/ii_structure/backends/golang.py`
- Modify: `src/ii_structure/backends/typescript.py`

- [ ] **Step 1: Implement `find_usages` in GoBackend**

```python
def find_usages(self, project_root, name, index, ...):
    lsp = LspClient(command=["gopls", "serve"], project_root=project_root)
    if not lsp.is_available():
        # Graceful degradation — name-based fallback
        return self._name_based_usages(name, index, ...,
            warning="Install gopls for type-resolved results: go install golang.org/x/tools/gopls@latest")
    # ... LSP-based resolution
```

Same pattern for TypeScriptBackend with `["typescript-language-server", "--stdio"]`.

- [ ] **Step 2: Implement `get_definition_source` in both backends**

Use the index to find candidates (same as Python). If only one candidate, read source directly. If ambiguous, use LSP `textDocument/definition` to resolve.

- [ ] **Step 3: Write integration tests (skip if server not installed)**

```python
@pytest.mark.skipif(not shutil.which("gopls"), reason="gopls not installed")
def test_go_usages_with_gopls(go_project):
    ...
```

- [ ] **Step 4: Test graceful degradation (always runs)**

```python
def test_go_usages_without_gopls(go_project, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: None)
    # Should still return name-based results with a warning
```

- [ ] **Step 5: Commit**

```bash
git add src/ii_structure/backends/ tests/
git commit -m "feat: LSP integration for Go and TypeScript usages with graceful degradation"
```

---

### Task 11: Update init command and help content

**Files:**
- Modify: `src/ii_structure/cli.py` (init command detects language servers)
- Modify: `src/ii_structure/help_content.yaml` (add multi-language info)

- [ ] **Step 1: Update init to detect language servers**

```
$ ii-structure init

Created CLAUDE.md with ii-structure instructions.

Languages detected:
  Python (.py):     ✓ full support (Jedi installed)
  Go (.go):         ⚠ structural only — install gopls for type-resolved usages:
                      go install golang.org/x/tools/gopls@latest
  TypeScript (.ts): ✓ full support (tsserver available)

Your AI agent will now use ii-structure automatically.
```

- [ ] **Step 2: Update help content**

Add to overview: "Supports Python, Go, and TypeScript. All commands work identically across languages."

Add language-specific tips to `usages` command help.

- [ ] **Step 3: Commit**

```bash
git add src/ii_structure/cli.py src/ii_structure/help_content.yaml
git commit -m "feat: init detects language servers, help updated for multi-language"
```

---

### Task 12: Full test suite, benchmarks, and push

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 2: Run benchmarks**

```bash
ii-structure benchmark run
```

- [ ] **Step 3: Manual verification**

```bash
# Go
ii-structure --project tests/fixtures/go_project files --summary
ii-structure --project tests/fixtures/go_project outline server/server.go --depth full
ii-structure --project tests/fixtures/go_project locate Server
ii-structure --project tests/fixtures/go_project body Server/Start

# TypeScript
ii-structure --project tests/fixtures/ts_project files --summary
ii-structure --project tests/fixtures/ts_project outline src/models.ts --depth full
ii-structure --project tests/fixtures/ts_project locate UserService
ii-structure --project tests/fixtures/ts_project body UserService/createUser

# Mixed
ii-structure files --summary  # should show .py + .go + .ts
```

- [ ] **Step 4: Push**

```bash
git push origin master
```
