# ii-structure

**Graph-backed structural code navigation, editing, and analysis for LLM agents. Supports Python, Go, and TypeScript.**

LLM coding agents burn thousands of tokens reading whole files and wading through noisy grep results to answer simple structural questions. ii-structure replaces "read text and filter mentally" with "ask a structural question, get a structural answer." All 12 commands (7 read, 2 write, 3 analysis) work identically across Python, Go, and TypeScript.

```
pip install ii-structure
```

---

## The Problem

An agent wants to know where `Index` is defined. With native tools:

```
$ grep "Index" src/ -r
28 lines of noise — imports, type hints, variable names, the actual definition buried in the middle
→ 566 tokens consumed
```

With ii-structure:

```
$ ii-structure locate Index --kind class
ok: true
command: locate
result:
- file: src/ii_structure/index.py
  line: 14
  kind: class
  name: Index
  signature: class Index
→ 52 tokens consumed (10.9x reduction)
```

## How It Works

ii-structure builds a **SQLite graph store** with nodes (symbols) and edges (calls, imports, test coverage). Language-specific parsers extract structure and relationships:

- **Python:** `ast` module (stdlib) + [Jedi](https://github.com/davidhalter/jedi) for type-resolved references
- **Go:** [tree-sitter](https://tree-sitter.github.io/) + optional [gopls](https://pkg.go.dev/golang.org/x/tools/gopls) for type-resolved references
- **TypeScript/TSX:** [tree-sitter](https://tree-sitter.github.io/) + optional [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server) for type-resolved references

```
Agent runs command → Index loads (or builds on first run) → Graph queried → Compact YAML returned
```

- **No server.** No daemon. No MCP. Each invocation is a fresh stateless process.
- **No config.** Auto-detects project root via `pyproject.toml` / `setup.py` / `go.mod` / `tsconfig.json` / `package.json` / `.git`.
- **Fast.** Structural commands complete in <300ms. Type-resolved `usages` in <1s.
- **Graceful degradation.** Language servers are optional — without them, `usages` falls back to index-based name matching.
- **Graph persistence.** SQLite stores pre-computed edges (call graph, import graph, test coverage) so analysis queries are instant lookups, not re-computation.

## Commands

### Read (structural, fast)

| Command | What it does | Example |
|---------|-------------|---------|
| `files` | List indexed files, or project map with `--summary` | `ii-structure files --summary --path src/` |
| `outline` | File skeleton — classes, functions, signatures. No bodies. | `ii-structure outline src/app.py --depth full` |
| `locate` | Find where a symbol is defined | `ii-structure locate User/save` |
| `body` | Full source of one symbol + content hash | `ii-structure body Index/build` |
| `usages` | Find all references, resolved by type | `ii-structure usages User/save --no-tests` |
| `imports` | Forward + reverse dependency graph | `ii-structure imports src/api.py --depth 2` |
| `search` | Ranked search over symbol names and docstrings | `ii-structure search authenticate` |

### Write (symbol-level code modification)

| Command | What it does | Example |
|---------|-------------|---------|
| `replace-body` | Replace a symbol's full source via stdin | `echo 'def save(self): pass' \| ii-structure replace-body User/save` |
| `insert-symbol` | Insert new code before/after a symbol via stdin | `echo 'def validate(self): pass' \| ii-structure insert-symbol --after User/save` |

Both write commands:
- **Auto-indent** — new code is re-indented to match the target symbol's level
- **`--expect-hash`** — pass the `content_hash` from `body` to reject the write if the file changed since the last read (optimistic concurrency)
- **Index auto-refresh** — the structural index and graph edges are updated after every write

**Safe write workflow:**
```bash
# 1. Read the symbol — get source + content_hash
ii-structure body User/save
# Returns: content_hash: sha256:a1b2c3d4...

# 2. Write with hash verification — rejected if file changed since step 1
echo 'def save(self):
    self.db.update(self.to_dict())
    return True' | ii-structure replace-body User/save --expect-hash sha256:a1b2c3d4...
```

### Analysis (graph-powered)

| Command | What it does | Example |
|---------|-------------|---------|
| `blast-radius` | What breaks if I change X? Affected symbols, files, and tests. | `ii-structure blast-radius User/save --depth 3` |
| `dead-code` | Find symbols with no callers (potentially dead code) | `ii-structure dead-code --file src/utils.py` |
| `test-coverage` | Which tests exercise a symbol (direct + transitive)? | `ii-structure test-coverage User/save` |

### Meta

| Command | What it does |
|---------|-------------|
| `help` | Structured YAML documentation — the agent's playbook |
| `init` | Creates `CLAUDE.md` so your AI agent uses ii-structure automatically |

## Agent Workflow

```
1. Map        →  ii-structure files --summary        (project map — every file + signatures)
2. Explore    →  ii-structure outline <file>          (file skeleton)
3. Find       →  ii-structure locate <name>           (definition location)
4. Read       →  ii-structure body <name>             (just the symbol, not the whole file)
5. Trace      →  ii-structure usages <name>           (all callers, type-resolved)
6. Deps       →  ii-structure imports <file>          (what depends on this?)
7. Analyze    →  ii-structure blast-radius <name>     (impact before refactoring)
8. Replace    →  ii-structure replace-body <name>     (rewrite a symbol via stdin)
9. Insert     →  ii-structure insert-symbol --after <name>  (add code next to a symbol)
```

The `help` command returns this workflow and per-command guidance as structured YAML — the agent reads it on first contact.

## Key Design Decisions

**Why `ast` for Python and tree-sitter for Go/TypeScript?**

Python's `ast` module gives identical structural extraction with zero native dependencies. For Go and TypeScript, tree-sitter provides fast, accurate parsing across languages. Type-resolved reference finding uses language-specific tooling: Jedi for Python, gopls for Go, typescript-language-server for TypeScript. Language servers are optional — structural commands always work, `usages` gracefully degrades to index-based name matching when servers aren't installed.

**Why graph persistence (SQLite over JSON)?**

The original JSON index stored flat symbol lists. Analysis queries like "what breaks if I change X?" required re-walking the entire index on every invocation. SQLite stores pre-computed edges (calls, imports, test coverage) so blast-radius, dead-code, and test-coverage are instant graph lookups. Edge extraction happens at index time — the cost is paid once, not per query. SQLite also handles concurrent access safely and scales to large codebases without loading the entire index into memory.

**Why include test files by default in `usages`?**

Every major tool (Sourcegraph, VS Code, Serena) includes tests by default. Excluding them during refactors causes agents to miss call sites and ship broken code. The `--no-tests` flag is opt-in for exploration.

**Why symbol-level writes instead of line-based edits?**

Every major AI coding tool (Claude Code, Aider, Cursor, Codex CLI) converged on content-addressed editing (search/replace or full rewrite) over line-number-based editing. Academic benchmarks confirm that LLMs reliably produce wrong line numbers — search/replace hits 94% accuracy while line-number formats hit 14-38%. `replace-body` is a full rewrite scoped to a single symbol, which is the sweet spot: the scope is small enough (5-50 lines) that full replacement is cheap, and the agent doesn't need to compute line numbers or exact `old_str` matches.

**Why YAML output?**

YAML is the most token-efficient structured format for LLMs — fewer quotes and braces than JSON. Every command returns the same envelope (`ok`, `command`, `result` or `error`) so the agent can parse responses uniformly.

## Installation

```bash
# With pipx (recommended for CLI tools)
pipx install git+https://github.com/somen4898/IntelligenceInterface.git

# Or with pip in a venv
pip install git+https://github.com/somen4898/IntelligenceInterface.git
```

Then set up your AI agent to use it:

```bash
cd your-project
ii-structure init
```

This creates a `CLAUDE.md` with usage instructions that your AI agent reads automatically every session. The agent will know when to use ii-structure vs native tools.

**Requirements:** Python 3.10+

**Dependencies:** jedi, pyyaml, click, pathspec, tree-sitter-language-pack

**Optional (for type-resolved usages in Go/TypeScript):**
```bash
# Go
go install golang.org/x/tools/gopls@latest

# TypeScript
npm install -g typescript-language-server typescript
```

## Development

```bash
git clone https://github.com/somen4898/IntelligenceInterface.git
cd IntelligenceInterface
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/       # 299 tests
```

## Project Structure

```
src/ii_structure/
├── cli.py              # Click entry point
├── parser.py           # Python ast-based symbol/import extraction
├── index.py            # Structural index with staleness detection
├── graph.py            # SQLite graph store (nodes, edges, analysis queries)
├── resolver.py         # Jedi-powered type resolution (Python)
├── lsp_client.py       # Generic LSP client for Go/TS language servers
├── output.py           # YAML envelope formatting
├── root.py             # Project root detection
├── help_content.yaml   # Agent playbook
├── backends/
│   ├── __init__.py     # Backend dispatcher (routes by file extension)
│   ├── base.py         # LanguageBackend protocol
│   ├── python.py       # Python backend (ast + Jedi)
│   ├── golang.py       # Go backend (tree-sitter + optional gopls)
│   └── typescript.py   # TypeScript backend (tree-sitter + optional tsserver)
└── commands/
    ├── files.py        # List indexed files
    ├── outline.py      # File skeleton
    ├── locate.py       # Find definitions
    ├── usages.py       # Type-resolved references
    ├── body.py         # Symbol source code
    ├── imports.py      # Dependency graph
    ├── search.py       # Ranked symbol search
    ├── replace_body.py # Replace symbol source
    ├── insert_symbol.py# Insert code by position
    ├── blast_radius.py # Impact analysis
    ├── dead_code.py    # Unused code detection
    ├── test_coverage.py# Structural test coverage
    └── help.py         # Agent documentation
```

## What This Is Not

- **Not a language server.** Uses LSP clients internally for type resolution, but ii-structure itself is just a CLI.
- **Not for humans.** Output is compact YAML optimized for token efficiency, not human aesthetics.
- **Not a replacement for grep.** When you need raw text search, use grep. ii-structure is for structural questions.

## License

MIT
