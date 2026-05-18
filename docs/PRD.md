# ii-structure — Product Requirements Document

**Version:** 1.0
**Date:** 2026-05-18
**Status:** Draft

---

## 1. Problem

LLM coding agents have limited context windows. Their native tools — Read, Glob, Grep — operate on raw text, not code structure. To answer a simple structural question like "where is this function defined and what calls it," an agent greps (gets dozens of mixed matches), reads whole files to verify, and burns thousands of tokens extracting one small fact.

There is no lightweight, stateless CLI tool that lets an agent ask structural questions about a Python codebase and get back compact, precise answers.

## 2. Solution

**ii-structure** is a command-line tool, installed via `pip`, that gives an LLM agent structural code navigation with minimal token cost. The agent runs `ii-structure <command>` from its shell and gets back compact YAML describing code structure — file skeletons, symbol locations, typed usages, definitions, imports.

It is:
- **Read-only** — never modifies source files
- **Stateless per invocation** — each command is a fresh process, no daemon, no server
- **Agent-optimized** — output is compact YAML designed for token efficiency, not human aesthetics
- **Type-aware** — uses Jedi for semantic resolution of references, not just name matching

## 3. Target User

LLM coding agents (Claude Code, aider, Cursor agent, etc.) operating in a shell environment. The tool is not designed for human developers as a primary audience. Humans can use it, but output is not optimized for human readability.

## 4. Command Surface

Seven navigation commands plus help. All return YAML to stdout, errors to stderr.

### 4.1 Structural Commands (ast-only, fast)

#### `files`
List indexed Python files.

```
ii-structure files [--glob PATTERN] [--path PREFIX]
```

Returns file paths, optionally filtered by glob pattern or path prefix.

#### `outline`
File skeleton: classes, functions, methods, signatures, docstrings, imports. No bodies.

```
ii-structure outline <file> [--depth top|full] [--kind class|function|import]
```

- `--depth top` — top-level symbols only (default)
- `--depth full` — includes nested symbols (methods inside classes, inner functions)
- `--kind` — restrict output to one symbol kind

#### `locate`
Find where a symbol is defined, by name path.

```
ii-structure locate <name> [--kind class|function|method|variable] [--file FILE]
```

Returns file, line, kind, signature, docstring. Supports substring matching. Returns a list when a name is ambiguous.

Name path examples:
- `User` — matches any symbol named User
- `User/save` — method `save` inside class `User`
- `/User` — leading slash anchors to file root (top-level only)

#### `imports`
What a file imports and what imports it.

```
ii-structure imports <file> [--depth N] [--include-external]
```

- `--depth` — hop distance (default 1, direct imports only)
- Excludes third-party packages by default
- High-degree hub nodes (`utils.py`, `__init__.py` re-exports) are de-emphasized

#### `search`
Lexical search over symbol names and docstrings.

```
ii-structure search <query>
```

Returns ranked matches. Searches symbol metadata, not file contents.

### 4.2 Type-Aware Commands (Jedi-powered)

#### `usages`
Every place a symbol is referenced, resolved by type.

```
ii-structure usages <name> [--path SCOPE] [--kind call|import|assignment|reference] [--limit N]
```

- Type-resolved: `user.save()` resolves to `User.save`, not every `.save()` call
- Path scope restricts search to a directory subtree
- Kind filter restricts to usage type
- Limit caps results (default 50), returns total count when truncated
- Each result includes file, line, usage kind, and one line of context

#### `body`
Full source body of one symbol.

```
ii-structure body <name> [--file FILE]
```

Uses Jedi to resolve which definition when the name is ambiguous across files. `--file` disambiguates explicitly.

### 4.3 Meta

#### `help`
Agent self-service interface.

```
ii-structure help [command]
```

- Without arguments: full command menu with usage guidance
- With argument: one command's detailed entry
- Each entry includes: description, when to use, when not to use, cost hint (fast/moderate), example invocation with example output
- Output is structured YAML — the agent reads this on first contact with the tool

## 5. Output Format

Every command returns a consistent YAML envelope:

**Success:**
```yaml
ok: true
command: locate
result:
  - file: src/models/user.py
    line: 34
    kind: class
    name: User
    signature: "class User(BaseModel)"
    docstring: "Core user entity"
```

**Error:**
```yaml
ok: false
command: locate
error: "No symbol matching 'Usr' found"
suggestion: "Did you mean 'User'? Try: ii-structure locate User"
```

**Truncated results:**
```yaml
ok: true
command: usages
result:
  - file: src/views.py
    line: 23
    kind: call
    context: "user.save()"
  # ... more results
total: 47
truncated: true
limit: 20
```

Design principles:
- Errors go to stderr separately from YAML on stdout, so output pipes cleanly
- One line of context per result, not a paragraph
- No syntax highlighting, no color codes, no terminal formatting
- Every field name is short and unambiguous

## 6. Project Root and State

**Root detection:** Walk up from cwd to first `pyproject.toml`, `setup.py`, `setup.cfg`, or `.git`. `--project PATH` overrides.

**State directory:** `<root>/.ii-structure/`
- Should be added to `.gitignore`
- Contains the structural index and Jedi's cache
- Can be safely deleted — rebuilt on next invocation

**File discovery:**
- Walks project tree, respects `.gitignore`
- Skips: `venv/`, `.venv/`, `__pycache__/`, `.git/`, `node_modules/`, `*.pyc`, `.ii-structure/`
- Only indexes `.py` files

## 7. Benchmarking

Benchmarking is a first-class part of the project. It ships with the tool and runs as a CLI command.

### 7.1 Benchmark Infrastructure

```
ii-structure benchmark run [--query NAME]
ii-structure benchmark compare <baseline-file>
```

- `benchmarks/corpus/` — a pinned Python project (git submodule, locked commit)
- `benchmarks/queries/` — YAML query definitions with archetype tags and correctness rubrics
- `benchmarks/baselines/` — stored results from previous runs

### 7.2 Query Archetypes

30-40 queries across four archetypes:
1. **Find known thing** — "Where is class X defined?" (exact match rubric)
2. **Find unknown thing** — "What handles authentication?" (must-contain rubric)
3. **Understand something** — "What does module X depend on?" (checklist rubric)
4. **Modify something** — "What would I need to change to rename X?" (completeness rubric)

### 7.3 What Is Measured

Per query:
- **Output size** — bytes of YAML returned (proxy for token cost)
- **Commands issued** — how many ii-structure invocations to answer the query
- **Wall-clock time** — tool execution time (not LLM inference)
- **Correctness** — against per-query rubric

### 7.4 Regression Policy

- Every PR runs `ii-structure benchmark run` in CI
- Results are compared against the current baseline
- A regression in output size or correctness blocks merge, or must be explicitly justified

### 7.5 Success Target

Against the benchmark corpus, ii-structure should enable an agent to reach correct answers with at least **3x fewer tokens** compared to a native-tools-only baseline (Read + Glob + Grep), with equal or better accuracy.

## 8. Installation

```
pip install ii-structure
```

**Dependencies:** jedi, pyyaml, click, pathspec. Everything else is stdlib.
**Python version:** 3.10+

## 9. Non-Goals

- **Not a language server.** No LSP, no MCP, no protocol.
- **Not multi-language in v1.** Python only. Architecture allows swapping the parser backend later.
- **Not for humans.** No color, no interactive mode, no TUI.
- **Not a code editor.** Read-only. Never modifies files.
- **Not a replacement for grep.** When the agent needs raw text search, it should use grep. ii-structure is for structural questions.

## 10. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Jedi cold start too slow (>5s) on large projects | Medium | Jedi caches aggressively; first call is slow, subsequent calls are fast. Document this. |
| Generic symbol names produce large result sets despite Jedi | Low | Jedi resolves by type, so `get` on a specific class returns only that class's usages. Path scope and limit cap worst cases. |
| ast module misses edge cases (eval, exec, dynamic code) | Low | These are invisible to any static tool. Document the limitation. |
| Benchmark corpus doesn't represent real-world usage | Medium | Choose a well-structured project with realistic patterns. Expand corpus over time. |
