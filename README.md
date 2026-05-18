# ii-structure

**Structural code navigation for LLM agents. 14.6x fewer tokens than grep + read on real projects.**

LLM coding agents burn thousands of tokens reading whole files and wading through noisy grep results to answer simple structural questions. ii-structure replaces "read text and filter mentally" with "ask a structural question, get a structural answer."

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

## Token Savings — Measured, Not Claimed

All numbers measured with `tiktoken`, comparing native tools (grep, cat/read) against ii-structure on identical queries.

### Real-World Project (production codebase)

| Task | Native Tokens | ii-structure Tokens | Reduction |
|------|:---:|:---:|:---:|
| File structure overview | 1,571 | 237 | **6.6x** |
| Find all usages of a symbol | 13,361 | 105 | **127.2x** |
| Production usages (no tests) | 13,109 | 105 | **124.8x** |
| Read single function | 1,571 | 1,823 | 0.9x |
| Search for 'config' | 16,918 | 126 | **134.3x** |
| **Total** | **33,421** | **2,291** | **14.6x** |

### Self-Referential (ii-structure's own codebase)

| Task | Native Tokens | ii-structure Tokens | Reduction |
|------|:---:|:---:|:---:|
| Find a class definition | 566 | 52 | **10.9x** |
| Understand a module's structure | 1,744 | 645 | **2.7x** |
| Find all callers of a function | 328 | 571 | 0.6x* |
| Read one method's implementation | 1,272 | 159 | **8.0x** |
| **Total** | **3,910** | **1,427** | **2.7x** |

The pattern: savings scale with project size. On a small codebase (1.3k lines), grep is tolerable — 2.7x savings. On a real project, grep returns thousands of noisy matches and files are longer — 14.6x savings. Larger projects = bigger wins.

*\*`usages` on the small codebase returns more than grep because it includes test files with classification. Use `--no-tests` to save 33% when exploring.*

## How It Works

ii-structure parses Python files with the `ast` module (stdlib) and uses [Jedi](https://github.com/davidhalter/jedi) for type-resolved reference finding. It maintains a lightweight JSON index that auto-updates when files change.

```
Agent runs command → Index loads (or builds on first run) → Query executes → Compact YAML returned
```

- **No server.** No daemon. No MCP. Each invocation is a fresh stateless process.
- **No config.** Auto-detects project root via `pyproject.toml` / `setup.py` / `.git`.
- **Fast.** Structural commands complete in <300ms. Type-resolved `usages` in <1s.

## Commands

### Structural (ast-only, fast)

| Command | What it does | Example |
|---------|-------------|---------|
| `files` | List indexed files | `ii-structure files --glob '*model*'` |
| `outline` | File skeleton — classes, functions, signatures. No bodies. | `ii-structure outline src/app.py --depth full` |
| `locate` | Find where a symbol is defined | `ii-structure locate User/save` |
| `imports` | Forward + reverse dependency graph | `ii-structure imports src/api.py --depth 2` |
| `search` | Ranked search over symbol names and docstrings | `ii-structure search authenticate` |

### Type-Aware (Jedi-powered)

| Command | What it does | Example |
|---------|-------------|---------|
| `usages` | Find all references, resolved by type | `ii-structure usages User/save --no-tests` |
| `body` | Full source of one symbol | `ii-structure body Index/build` |

### Meta

| Command | What it does |
|---------|-------------|
| `help` | Structured YAML documentation — the agent's playbook |

## Agent Workflow

```
1. Orient     →  ii-structure files
2. Explore    →  ii-structure outline <file>
3. Find       →  ii-structure locate <name>
4. Read       →  ii-structure body <name>
5. Trace      →  ii-structure usages <name>
6. Deps       →  ii-structure imports <file>
```

The `help` command returns this workflow and per-command guidance as structured YAML — the agent reads it on first contact.

## Key Design Decisions

**Why `ast` + Jedi, not tree-sitter?**

Tree-sitter is a parser — it gives you syntax trees but no type information. When you search for `save()`, tree-sitter finds every `.save()` call in the project. Jedi knows that `user.save()` calls `User.save` specifically, not `Product.save`. For Python, `ast` gives identical structural extraction with zero native dependencies, and Jedi adds semantic resolution that tree-sitter cannot provide. Tree-sitter is the planned multi-language backend for v2.

**Why include test files by default in `usages`?**

Every major tool (Sourcegraph, VS Code, Serena) includes tests by default. Excluding them during refactors causes agents to miss call sites and ship broken code. The `--no-tests` flag is opt-in for exploration.

**Why YAML output?**

YAML is the most token-efficient structured format for LLMs — fewer quotes and braces than JSON. Every command returns the same envelope (`ok`, `command`, `result` or `error`) so the agent can parse responses uniformly.

## Benchmarks

Benchmarks ship with the tool and run as a CLI command:

```
$ ii-structure benchmark run

ID                   Arch               Bytes  Cmds     Time  Pass
-----------------------------------------------------------------
find-known-1         find-known           165     1    0.20s     ✓
find-known-2         find-known           223     1    0.15s     ✓
find-known-3         find-known           380     1    0.15s     ✓
find-unknown-1       find-unknown        2111     1    0.15s     ✓
find-unknown-2       find-unknown         410     1    0.15s     ✓
modify-1             modify              1994     1    0.39s     ✓
modify-2             modify               571     1    0.20s     ✓
understand-1         understand          2228     1    0.15s     ✓
understand-2         understand           575     1    0.15s     ✓
understand-3         understand           754     1    0.16s     ✓
-----------------------------------------------------------------
Total: 10 queries, 10/10 correct, 9411 bytes
```

10 queries across 4 archetypes (find-known, find-unknown, understand, modify). Regression detection via `ii-structure benchmark compare`.

## Installation

```bash
pip install ii-structure
```

**Requirements:** Python 3.10+

**Dependencies:** jedi, pyyaml, click, pathspec — all pure Python except Jedi's optional C extensions.

## Development

```bash
git clone https://github.com/somen4898/IntelligenceInterface.git
cd IntelligenceInterface
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/       # 130 tests
```

## Project Structure

```
src/ii_structure/
├── cli.py              # Click entry point
├── parser.py           # ast-based symbol/import extraction
├── index.py            # Structural index with staleness detection
├── resolver.py         # Jedi-powered type resolution
├── output.py           # YAML envelope formatting
├── root.py             # Project root detection
├── help_content.yaml   # Agent playbook
└── commands/
    ├── files.py        # List indexed files
    ├── outline.py      # File skeleton
    ├── locate.py       # Find definitions
    ├── usages.py       # Type-resolved references
    ├── body.py         # Symbol source code
    ├── imports.py      # Dependency graph
    ├── search.py       # Ranked symbol search
    └── help.py         # Agent documentation
```

## What This Is Not

- **Not a language server.** No LSP, no MCP, no protocol. Just a CLI.
- **Not multi-language (yet).** Python only in v1. Architecture supports swapping to tree-sitter for v2.
- **Not for humans.** Output is compact YAML optimized for token efficiency, not human aesthetics.
- **Not a replacement for grep.** When you need raw text search, use grep. ii-structure is for structural questions.

## License

MIT
