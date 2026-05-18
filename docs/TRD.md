# ii-structure — Technical Requirements Document

**Version:** 1.0
**Date:** 2026-05-18
**Status:** Draft

---

## 1. Architecture Overview

ii-structure is a stateless CLI tool. Each invocation is a fresh process that:

1. Detects the project root
2. Loads or builds the structural index
3. Checks staleness for files relevant to the query
4. Executes the query (ast-only or ast + Jedi)
5. Formats and returns YAML to stdout
6. Exits

There is no background process, no daemon, no socket, no server. The tool's only persistent state is the index directory on disk.

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                      │
│              cli.py (click)                       │
│    Parses args → dispatches to command module     │
├─────────────────────────────────────────────────┤
│                 Command Layer                     │
│   commands/{files,outline,locate,usages,...}.py   │
│     Each command: load index → query → format     │
├──────────────────────┬──────────────────────────┤
│    Parser Module     │    Resolver Module        │
│    parser.py         │    resolver.py            │
│    ast-based         │    Jedi-powered           │
│    extraction        │    type resolution        │
├──────────────────────┴──────────────────────────┤
│                  Index Layer                      │
│                 index.py                          │
│   Build, load, staleness check, update            │
├─────────────────────────────────────────────────┤
│                 Output Layer                      │
│                output.py                          │
│   YAML envelope formatting, error formatting      │
└─────────────────────────────────────────────────┘
```

## 2. Module Specifications

### 2.1 `cli.py` — Entry Point

**Responsibility:** Parse CLI arguments, dispatch to the correct command module, handle top-level errors.

**Framework:** click

**Entry point:** `ii-structure` console script registered in `pyproject.toml`.

**Global options:**
- `--project PATH` — override project root detection
- `--no-cache` — rebuild index from scratch (ignore existing)

**Error handling:** Any uncaught exception is caught at the top level, formatted as a YAML error envelope, and returned with exit code 1. Tracebacks go to stderr only.

### 2.2 `index.py` — Structural Index

**Responsibility:** Build, persist, load, and incrementally update the per-file structural index.

**Index location:** `<project_root>/.ii-structure/index.json`

**Index schema:**
```json
{
  "version": 1,
  "project_root": "/absolute/path",
  "files": {
    "src/models/user.py": {
      "mtime": 1716048000.0,
      "content_hash": "sha256:abc123...",
      "symbols": [...],
      "imports": [...],
      "parse_error": null
    }
  }
}
```

**Symbol entry schema:**
```json
{
  "name": "User",
  "kind": "class",
  "line": 34,
  "end_line": 89,
  "signature": "class User(BaseModel)",
  "docstring": "Core user entity",
  "parent": null,
  "children": ["__init__", "save", "delete"]
}
```

**Import entry schema:**
```json
{
  "module": "sqlalchemy.orm",
  "names": ["Session", "relationship"],
  "alias": null,
  "line": 3,
  "is_relative": false
}
```

**File discovery:**
- Walk project tree starting from project root
- Respect `.gitignore` via `pathspec` library (lightweight, pure Python)
- Hard-coded skip list: `venv/`, `.venv/`, `__pycache__/`, `.git/`, `node_modules/`, `.ii-structure/`, `*.pyc`
- Only index files ending in `.py`

**Staleness detection:**
1. On index load, the command declares which files it needs (or all files for broad queries)
2. For each needed file, compare stored `mtime` against filesystem `mtime`
3. If `mtime` differs, compute `sha256` of file contents
4. If hash differs, re-parse that file with `parser.py` and update the index entry
5. If file no longer exists, remove it from the index
6. New `.py` files not in the index are parsed and added
7. Write updated index back to disk

**Performance target:** Index load + staleness check for a 50k-line project (200 files) should complete in <500ms when no files have changed.

### 2.3 `parser.py` — AST-Based Extraction

**Responsibility:** Parse a single Python file using `ast` and extract structural information: symbols (classes, functions, methods, variables), imports, docstrings, signatures.

**Interface:**
```python
def parse_file(file_path: str, source: str) -> ParseResult:
    """Parse a Python file and extract structural data.

    Returns ParseResult with symbols, imports, and any parse error.
    Raises nothing — parse errors are captured in the result.
    """
```

**What is extracted:**

| AST Node | Extracted As |
|---|---|
| `ast.ClassDef` | kind=class, name, bases (signature), docstring, line range |
| `ast.FunctionDef` inside class | kind=method, name, args (signature), decorators, docstring, line range |
| `ast.FunctionDef` at top level | kind=function, name, args (signature), decorators, docstring, line range |
| `ast.AsyncFunctionDef` | Same as FunctionDef, flagged as async |
| `ast.Import` | module name, aliases |
| `ast.ImportFrom` | module name, imported names, relative level |
| `ast.Assign` at module/class level | kind=variable, name, line (no type inference) |
| `ast.AnnAssign` at module/class level | kind=variable, name, annotation, line |

**Signature extraction:**
- Functions/methods: `def name(arg1: type, arg2: type) -> return_type`
- Classes: `class Name(Base1, Base2)`
- Includes decorators as a list

**Docstring extraction:**
- First `ast.Constant` string expression in function/class body
- Truncated to first 200 characters in the index (full docstring available via `body` command)

**Nesting:**
- Symbols maintain a `parent` field pointing to their containing symbol's name path
- `children` field lists direct child symbol names
- This builds the name path tree: `User/save`, `User/Meta/ordering`

**Error handling:**
- If `ast.parse()` raises `SyntaxError`, the result captures the error message and line number
- Partial results are not returned for syntax errors — the file gets an error entry

### 2.4 `resolver.py` — Jedi Type Resolution

**Responsibility:** Use Jedi to answer type-aware questions: where is a symbol used (resolved by type), and which definition does an ambiguous name refer to.

**Interface:**
```python
def find_usages(
    project_root: str,
    name: str,
    path_scope: str | None = None,
    kind_filter: str | None = None,
    limit: int = 50
) -> list[Usage]:
    """Find all usages of a symbol, resolved by type.

    Uses Jedi to resolve which definition each reference points to.
    Returns Usage objects with file, line, kind, context.
    """

def get_definition_source(
    project_root: str,
    name: str,
    file_hint: str | None = None
) -> DefinitionSource:
    """Get the full source body of a symbol.

    Uses Jedi to resolve ambiguous names.
    Returns the source code and location.
    """
```

**Jedi integration details:**

1. **Project setup:** Create `jedi.Project(path=project_root)` once per invocation. Jedi discovers virtualenvs and sys.path automatically.

2. **Name resolution for `usages`:**
   - First, use the ast index to find all definitions matching `name` (via name path)
   - For each definition, create a `jedi.Script` at that file/line
   - Call `.get_references()` to get type-resolved usages
   - Filter by `path_scope`, `kind_filter`, and `limit`
   - Return deduplicated, sorted results

3. **Name resolution for `body`:**
   - If `--file` is provided, use `jedi.Script` at that file to find the definition
   - If not, use the ast index to find candidates, then use Jedi to resolve
   - Extract full source from `definition.line` to `definition.end_line` (or re-read from `ast` using the line range from the index)

4. **Jedi caching:** Jedi maintains its own cache in `~/.cache/jedi/` by default. We configure it to use `<project_root>/.ii-structure/jedi/` instead, keeping all tool state in one place.

**Performance considerations:**
- First Jedi call on a project with heavy dependencies (django, pandas) may take 2-5s
- Subsequent calls use Jedi's warm cache and complete in 50-200ms
- The ast index is used to narrow scope before calling Jedi, avoiding full-project Jedi scans

### 2.5 `commands/` — Command Implementations

Each command module follows the same pattern:

```python
def execute(index: Index, **kwargs) -> dict:
    """Execute the command and return the result dict.

    The CLI layer handles YAML formatting.
    """
```

#### `commands/files.py`
- Load index, return file list
- Apply glob/path filters using `fnmatch` or `pathlib.match`
- Jedi: no

#### `commands/outline.py`
- Load index, find the file entry
- Return symbols filtered by depth and kind
- Format signatures and docstrings
- Jedi: no

#### `commands/locate.py`
- Load index, search all files for matching symbol name paths
- Support exact match, substring match, and anchored match (leading `/`)
- Filter by kind
- Filter by file if `--file` provided
- Jedi: no

#### `commands/usages.py`
- Use ast index to find the definition(s) matching the name
- Pass to `resolver.find_usages()` for type-resolved references
- Apply path scope, kind filter, limit
- Return results with one line of source context each
- Jedi: yes

#### `commands/body.py`
- Use ast index to find candidates
- If only one candidate, read source directly from disk (skip Jedi)
- If ambiguous and no `--file`, use `resolver.get_definition_source()` to resolve
- Read the source file and extract lines from start to end of the symbol
- Jedi: yes (for disambiguation only)

#### `commands/imports.py`
- Load index, read import entries for the target file
- For depth > 1, recursively follow imports through the index
- For reverse direction (what imports this file), scan all index entries
- Exclude third-party by default (imports not resolvable to a project file)
- De-emphasize high-degree nodes: files imported by >10 other files are marked with `hub: true` in output, letting the agent decide whether to follow them
- Jedi: no

#### `commands/search.py`
- Load index, search symbol names and docstrings
- Ranking: exact name match > prefix match > substring match > docstring match
- Return top N results (default 20)
- Jedi: no

#### `commands/help.py`
- Load `help_content.yaml` bundled with the package
- Return full menu or single command entry
- Each entry: description, when_to_use, when_not_to_use, cost_hint, example_input, example_output
- Jedi: no

### 2.6 `output.py` — YAML Formatting

**Responsibility:** Format command results into the standard YAML envelope.

```python
def format_success(command: str, result: Any) -> str:
    """Format a successful result as YAML."""

def format_error(command: str, error: str, suggestion: str | None = None) -> str:
    """Format an error as YAML."""
```

- Uses `pyyaml` with `default_flow_style=False` for readable output
- Ensures consistent field ordering: `ok`, `command`, `result`/`error`
- Handles truncation: adds `total` and `truncated` fields when limit is hit
- No color codes, no ANSI escapes, no terminal formatting

### 2.7 `help_content.yaml` — Agent Interface Documentation

Structured YAML bundled with the package. Not generated — hand-written and maintained.

```yaml
commands:
  outline:
    description: "File skeleton: classes, functions, signatures, docstrings. No bodies."
    when_to_use: "First step when exploring an unfamiliar file. Cheaper than reading the whole file."
    when_not_to_use: "When you need the full implementation. Use body for a specific symbol or Read for the whole file."
    cost: fast
    example:
      input: "ii-structure outline src/models/user.py"
      output: |
        ok: true
        command: outline
        result:
          file: src/models/user.py
          symbols:
            - name: User
              kind: class
              line: 34
              signature: "class User(BaseModel)"
              docstring: "Core user entity"
              children:
                - name: __init__
                  kind: method
                  line: 38
                  signature: "def __init__(self, name: str, email: str)"
                - name: save
                  kind: method
                  line: 52
                  signature: "def save(self) -> None"
```

## 3. Package Structure

```
ii-structure/
├── pyproject.toml
├── src/
│   └── ii_structure/
│       ├── __init__.py          # version
│       ├── cli.py               # click entry point
│       ├── index.py             # index build/load/update
│       ├── parser.py            # ast extraction
│       ├── resolver.py          # Jedi integration
│       ├── output.py            # YAML envelope formatting
│       ├── help_content.yaml    # agent help data
│       └── commands/
│           ├── __init__.py
│           ├── files.py
│           ├── outline.py
│           ├── locate.py
│           ├── usages.py
│           ├── body.py
│           ├── imports.py
│           ├── search.py
│           └── help.py
├── benchmarks/
│   ├── corpus/                  # git submodule, pinned commit
│   ├── queries/                 # YAML query definitions + rubrics
│   ├── baselines/               # stored results for regression
│   └── runner.py                # benchmark execution logic
├── tests/
│   ├── conftest.py              # shared fixtures
│   ├── test_parser.py
│   ├── test_index.py
│   ├── test_resolver.py
│   ├── test_commands/
│   │   ├── test_files.py
│   │   ├── test_outline.py
│   │   ├── test_locate.py
│   │   ├── test_usages.py
│   │   ├── test_body.py
│   │   ├── test_imports.py
│   │   ├── test_search.py
│   │   └── test_help.py
│   └── fixtures/                # small Python projects for testing
│       ├── simple_project/
│       └── complex_project/
└── .gitignore
```

## 4. Dependencies

### Runtime
| Package | Version | Purpose |
|---|---|---|
| `jedi` | >=0.19 | Type inference for `usages` and `body` |
| `pyyaml` | >=6.0 | YAML output formatting |
| `click` | >=8.0 | CLI framework |
| `pathspec` | >=0.11 | .gitignore pattern matching |

### Development
| Package | Version | Purpose |
|---|---|---|
| `pytest` | >=7.0 | Testing |
| `pytest-cov` | >=4.0 | Coverage |

### Transitive (via Jedi)
| Package | Purpose |
|---|---|
| `parso` | Python parser (Jedi's dependency) |

**Total install footprint:** ~25MB (Jedi + parso + stubs account for ~20MB)

**Python version:** >=3.10

## 5. Index Performance Budget

| Operation | Target | Notes |
|---|---|---|
| Full index build (200 files, 50k lines) | <3s | ast.parse is ~1ms/file, dominated by I/O |
| Index load from disk | <100ms | JSON parse of index file |
| Staleness check (no changes) | <200ms | stat() calls on 200 files |
| Staleness check + 5 file re-parse | <500ms | 5 files * ast.parse + index rewrite |
| `outline` command (cached) | <300ms | Index load + filter + YAML format |
| `locate` command (cached) | <300ms | Index load + search + YAML format |
| `usages` command (Jedi warm) | <1s | Index load + Jedi resolution |
| `usages` command (Jedi cold) | <5s | First Jedi call, dependency parsing |
| `imports` depth 1 | <300ms | Index load + single-hop lookup |
| `imports` depth 2 | <500ms | Two-hop traversal |

## 6. Benchmark Infrastructure

### 6.1 Corpus

A pinned Python project included as a git submodule at `benchmarks/corpus/`. Requirements:
- 15k-40k lines of Python
- Well-typed (type annotations present)
- Multiple packages/modules (non-trivial navigation)
- Not mega-popular (reduces LLM memorization risk)
- Has tests (enables "modify" archetype queries)

Locked to a specific commit. Never updated without re-running all benchmarks.

### 6.2 Query Definition Format

```yaml
id: find-known-1
archetype: find-known
description: "Find the definition of the User class"
commands:
  - "ii-structure locate User --kind class"
rubric:
  type: exact-match
  expected:
    file: "src/models/user.py"
    line: 34
    kind: class
```

```yaml
id: understand-3
archetype: understand
description: "What does the auth module depend on?"
commands:
  - "ii-structure imports src/auth/ --depth 2"
rubric:
  type: must-contain
  expected_items:
    - "src/models/user.py"
    - "src/db/session.py"
```

### 6.3 Runner

`ii-structure benchmark run` executes each query:
1. Runs the commands listed in the query
2. Captures stdout (YAML output)
3. Measures output size in bytes, number of commands, wall-clock time
4. Evaluates correctness against the rubric
5. Writes results to `benchmarks/baselines/<timestamp>.json`

`ii-structure benchmark compare <baseline>` diffs the current run against a previous baseline and reports regressions.

### 6.4 CI Integration

GitHub Actions workflow runs `ii-structure benchmark run` on every PR. Compares against `benchmarks/baselines/current.json`. Fails the check if:
- Any query's correctness drops from pass to fail
- Aggregate output size increases by >10%

## 7. Testing Strategy

### 7.1 Unit Tests

- `test_parser.py` — parse various Python constructs, verify extracted symbols/imports/docstrings. Test edge cases: decorators, async functions, nested classes, syntax errors, empty files, files with only imports.
- `test_index.py` — build index, verify staleness detection, verify incremental update, verify file deletion handling, verify new file detection.
- `test_resolver.py` — Jedi resolution for usages and body. Test: simple case, method on specific class vs generic name, cross-file reference, ambiguous name with file hint.

### 7.2 Command Tests

Each command has its own test file. Tests run against fixture projects in `tests/fixtures/`:

- `simple_project/` — 3-5 files, basic classes/functions/imports. For happy-path testing.
- `complex_project/` — 15-20 files, inheritance, cross-module imports, generic names, decorators, async code. For edge-case testing.

Tests invoke the command function directly (not through CLI) and assert on the result dict.

### 7.3 Integration Tests

End-to-end tests that invoke `ii-structure` as a subprocess and verify YAML output. Cover:
- First run (index build from scratch)
- Second run (cached, no changes)
- File modification between runs (staleness + re-parse)
- File deletion between runs
- Malformed Python file (syntax error)
- Empty project
- `--project` flag override

### 7.4 Coverage Target

80% line coverage minimum. `resolver.py` may be lower due to Jedi integration complexity.

## 8. Error Handling

| Scenario | Behavior |
|---|---|
| Project root not found | YAML error + suggestion to use `--project` |
| File not found | YAML error with the path that was tried |
| File has syntax error | YAML error with line number and message. File marked as errored in index. |
| Symbol not found | YAML error + suggestion (fuzzy match on name) |
| Jedi timeout/crash | YAML error explaining Jedi failed, suggest using `locate` (ast-only) as fallback |
| Index file corrupted | Delete and rebuild silently |
| Permission denied on file | Skip file, log warning to stderr |
| `--limit` exceeded | Return truncated results with `total` count |

All errors return exit code 1. All errors produce valid YAML on stdout. Tracebacks and warnings go to stderr only.

## 9. Future Considerations (Not in v1)

- **Multi-language support:** Replace `parser.py` with tree-sitter backend. The command surface and output format stay the same.
- **MCP server mode:** Wrap the CLI in an MCP server for agents that support it.
- **Watch mode:** `ii-structure watch` keeps the index hot. Only if cold starts prove to be a problem.
- **Scope-aware search:** Use Jedi's scope information to filter `locate` results by reachability from a given file.
