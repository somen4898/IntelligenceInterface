# Phase 3: files, imports, search, help

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the command surface — add `files`, `imports`, `search`, and `help` commands.

**Architecture:** All four commands are ast-index-only (no Jedi). `files` lists indexed files. `imports` builds a dependency graph from index import data. `search` does ranked lexical search over symbol names and docstrings. `help` returns structured YAML from a bundled help file.

**Tech Stack:** Existing stack, no new dependencies.

---

### Task 1: files command

**Files:**
- Create: `src/ii_structure/commands/files.py`
- Create: `tests/test_commands/test_files.py`
- Modify: `src/ii_structure/cli.py`

### Task 2: imports command

**Files:**
- Create: `src/ii_structure/commands/imports.py`
- Create: `tests/test_commands/test_imports.py`
- Modify: `src/ii_structure/cli.py`

### Task 3: search command

**Files:**
- Create: `src/ii_structure/commands/search.py`
- Create: `tests/test_commands/test_search.py`
- Modify: `src/ii_structure/cli.py`

### Task 4: help command

**Files:**
- Create: `src/ii_structure/help_content.yaml`
- Create: `src/ii_structure/commands/help.py`
- Create: `tests/test_commands/test_help.py`
- Modify: `src/ii_structure/cli.py`

### Task 5: Full suite + verify
