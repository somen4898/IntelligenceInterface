# Implementation Prompt: Write Commands for ii-structure

## Context

You are adding write capabilities to `ii-structure`, a CLI tool that provides structural code navigation for AI agents. The tool currently supports read-only operations (outline, locate, body, search, imports, usages, files, help). You are adding two new commands: `replace-body` and `insert-symbol`.

**Repository:** `/Users/somen/Projects/ii-structure`
**Branch:** Create `feature/write-commands` from `master`

---

## Goal

Add two write commands that let agents modify code by symbol name instead of raw text replacement. This eliminates the need for agents to compute `old_str` for `str_replace`, halving output tokens on typical edits and avoiding whitespace/uniqueness failure modes.

---

## Architecture You Must Follow

The codebase has a strict pattern. Every command follows this flow:

```
cli.py (Click command) → commands/<name>.py (execute function) → backends or resolver
```

**Key files you must understand before writing code:**

| File | What it does |
|------|-------------|
| `src/ii_structure/cli.py` | Click CLI entry point. Each command is a `@cli.command()` function that calls `execute()` from its command module |
| `src/ii_structure/commands/body.py` | Example read command — resolves symbol via index, dispatches to backend |
| `src/ii_structure/resolver.py` | Python backend's symbol resolution. `_read_symbol_source()` at line 163 reads a symbol's source using `line` and `end_line` from the index |
| `src/ii_structure/parser.py` | Defines `SymbolInfo(name, kind, line, end_line, signature, docstring, parent, children, decorators)`, `ImportInfo`, `ParseResult` |
| `src/ii_structure/index.py` | `Index` class — stores parsed symbols per file, supports `search_symbols(name_path)` which returns `list[dict]` with fields from SymbolInfo plus `"file"` |
| `src/ii_structure/output.py` | `format_success(command, result)` and `format_error(command, error, suggestion)` — all CLI output goes through these, producing YAML envelopes |
| `src/ii_structure/backends/base.py` | `LanguageBackend` Protocol with `parse_file`, `find_usages`, `get_definition_source` |
| `src/ii_structure/backends/__init__.py` | `get_backend(file_path)` dispatches `.py` → PythonBackend, `.go` → GoBackend, `.ts/.tsx` → TypeScriptBackend |

**Data flow for symbol resolution (you will reuse this):**

1. `index.search_symbols("User/save")` returns candidates with `file`, `line`, `end_line`, `name`, `kind`, `parent`
2. Read the file from disk
3. Slice `lines[line-1 : end_line]` to get the symbol's source (note: `line` and `end_line` are 1-indexed)

**Important detail about line slicing:** In `resolver.py:168-171`, the existing code does:
```python
start = candidate["line"] - 1      # convert to 0-indexed
end = candidate.get("end_line", candidate["line"])  # stays 1-indexed
body = "\n".join(lines[start:end])  # Python slice is exclusive on end, so this works correctly
                                     # because 1-indexed end_line == 0-indexed exclusive end
```
This is actually correct: if a symbol spans lines 10-15 (1-indexed), then `lines[9:15]` gives lines 9,10,11,12,13,14 which is 6 lines (lines 10-15 inclusive). Maintain this same convention in your write code.

---

## Command 1: `replace-body`

### What it does

Replaces the full source of an existing symbol (function, method, or class) with new source code provided via stdin.

### CLI interface

```bash
# Pipe new source via stdin
echo 'def save(self):
    self.validate()
    self.db.update(self.to_dict())
    return True' | ii-structure replace-body User/save

# With file hint for disambiguation
echo '...' | ii-structure replace-body save --file src/models/user.py
```

### Click command definition (add to `cli.py`)

```python
@cli.command("replace-body")
@click.argument("name")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.pass_context
def replace_body(ctx, name, file_hint):
    """Replace the full source of a symbol with new code from stdin."""
    import sys
    if sys.stdin.isatty():
        click.echo(format_error("replace-body", "No input on stdin. Pipe the new body.",
                   suggestion="echo 'new code' | ii-structure replace-body Symbol/name"))
        sys.exit(1)
    new_body = sys.stdin.read()
    try:
        idx = _get_index(ctx)
        root = str(ctx.obj["root"])
        from ii_structure.commands.replace_body import execute
        result = execute(idx=idx, project_root=root, name=name,
                        new_body=new_body, file_hint=file_hint)
        click.echo(format_success("replace-body", result))
    except Exception as e:
        click.echo(format_error("replace-body", str(e)))
        sys.exit(1)
```

### Command module: `src/ii_structure/commands/replace_body.py`

```python
def execute(
    idx: Index,
    project_root: str,
    name: str,
    new_body: str,
    file_hint: str | None = None,
) -> dict:
    """Replace the full source of a symbol with new code.

    Resolves the symbol via the index, reads the file, splices out the old
    source at [line, end_line], splices in the new body with matched
    indentation, writes the file, and refreshes the index.
    """
```

### Implementation requirements

1. **Resolve the symbol** using `idx.search_symbols(name)`. If `file_hint` is provided, filter candidates by file. Error if zero or multiple candidates found (multiple = ambiguous, tell the agent to use `--file`).

2. **Read the file** from disk. Get the full content as lines.

3. **Detect indentation** of the existing symbol. The indentation is the whitespace prefix of `lines[candidate["line"] - 1]` (the first line of the symbol). For example, if the symbol starts with `    def save(self):`, the indent is 4 spaces.

4. **Indent the new body** to match. The new body from stdin may or may not be indented. Apply this logic:
   - Strip all leading whitespace from the first line of `new_body` to detect its base indent
   - Compute the delta between the existing indent and the new body's base indent
   - Re-indent all lines of `new_body` to match the existing symbol's indentation
   - Handle the case where `new_body` has zero indentation (common — agents often write unindented code)

5. **Splice** the new body into the file content:
   ```python
   start = candidate["line"] - 1      # 0-indexed inclusive
   end = candidate.get("end_line", candidate["line"])  # 0-indexed exclusive (see convention above)
   new_lines = file_lines[:start] + indented_new_body_lines + file_lines[end:]
   ```

6. **Write the file** back to disk.

7. **Refresh the index** for that file only. Call `idx.refresh()` or manually re-parse just the changed file:
   ```python
   from ii_structure.index import _parse_and_build_entry
   import pathlib
   source_file = pathlib.Path(project_root) / candidate["file"]
   idx.files[candidate["file"]] = _parse_and_build_entry(source_file)
   idx.save(pathlib.Path(project_root) / ".ii-structure")
   ```

8. **Return structured result:**
   ```python
   {
       "file": candidate["file"],
       "symbol": name,
       "lines_removed": old_end - old_start,
       "lines_added": len(indented_new_body_lines),
       "new_range": [candidate["line"], candidate["line"] + len(indented_new_body_lines) - 1],
   }
   ```

### Error cases to handle

- No candidates found → `"Symbol '{name}' not found in index"`
- Multiple candidates, no file_hint → `"Multiple definitions found for '{name}'. Use --file to disambiguate."` with suggestion listing the files
- Stdin is empty → `"Empty replacement body"`
- File doesn't exist on disk → `"File '{file}' not found on disk"`

---

## Command 2: `insert-symbol`

### What it does

Inserts new code at a structural position relative to an existing symbol. Supports `--after` and `--before` positioning.

### CLI interface

```bash
# Insert a new method after User/save
echo 'def validate(self):
    if not self.name:
        raise ValueError("name required")' | ii-structure insert-symbol --after User/save

# Insert before a function
echo 'def setup():
    configure_logging()' | ii-structure insert-symbol --before main
```

### Click command definition (add to `cli.py`)

```python
@cli.command("insert-symbol")
@click.option("--after", "after_symbol", default=None, help="Insert after this symbol")
@click.option("--before", "before_symbol", default=None, help="Insert before this symbol")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.pass_context
def insert_symbol(ctx, after_symbol, before_symbol, file_hint):
    """Insert new code before or after an existing symbol."""
    import sys
    if not after_symbol and not before_symbol:
        click.echo(format_error("insert-symbol", "Must specify --after or --before"))
        sys.exit(1)
    if after_symbol and before_symbol:
        click.echo(format_error("insert-symbol", "Specify only one of --after or --before"))
        sys.exit(1)
    if sys.stdin.isatty():
        click.echo(format_error("insert-symbol", "No input on stdin."))
        sys.exit(1)
    new_code = sys.stdin.read()
    try:
        idx = _get_index(ctx)
        root = str(ctx.obj["root"])
        from ii_structure.commands.insert_symbol import execute
        anchor = after_symbol or before_symbol
        position = "after" if after_symbol else "before"
        result = execute(idx=idx, project_root=root, anchor=anchor,
                        position=position, new_code=new_code, file_hint=file_hint)
        click.echo(format_success("insert-symbol", result))
    except Exception as e:
        click.echo(format_error("insert-symbol", str(e)))
        sys.exit(1)
```

### Command module: `src/ii_structure/commands/insert_symbol.py`

```python
def execute(
    idx: Index,
    project_root: str,
    anchor: str,
    position: str,  # "after" or "before"
    new_code: str,
    file_hint: str | None = None,
) -> dict:
    """Insert new code before or after an existing symbol.

    Resolves the anchor symbol, determines the insertion line,
    matches indentation to the anchor's level, inserts the code
    with a blank line separator, and refreshes the index.
    """
```

### Implementation requirements

1. **Resolve the anchor symbol** same as `replace-body`.

2. **Determine insertion line:**
   - `position == "after"`: insert at `candidate["end_line"]` (after the last line of the anchor symbol)
   - `position == "before"`: insert at `candidate["line"] - 1` (before the first line, including decorators)

3. **Match indentation** to the anchor symbol's indentation level (same logic as `replace-body`).

4. **Add blank line separators.** Insert one blank line between the anchor and the new code. Check if one already exists and don't double up.

5. **Splice and write** same as `replace-body`.

6. **Refresh the index** for the changed file.

7. **Return structured result:**
   ```python
   {
       "file": candidate["file"],
       "anchor": anchor,
       "position": position,
       "lines_added": len(indented_lines),
       "inserted_range": [insert_line, insert_line + len(indented_lines) - 1],
   }
   ```

---

## Tests

Create `tests/test_commands/test_replace_body.py` and `tests/test_commands/test_insert_symbol.py`.

Use TDD. Write tests first, then implement until they pass.

### Test file structure

Use the existing test fixtures pattern. Here's the test setup:

```python
import pathlib
import textwrap
import pytest
from ii_structure.index import Index

@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal Python project for write command tests."""
    src = tmp_path / "models.py"
    src.write_text(textwrap.dedent('''\
        class User:
            def __init__(self, name: str):
                self.name = name

            def save(self):
                print("saving")

            def delete(self):
                print("deleting")


        def helper():
            return 42
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx
```

### Tests for `replace-body`

1. **test_replace_simple_method** — Replace `User/save` body, verify file content and returned metadata
2. **test_replace_preserves_indentation** — New body has no indentation, verify it gets indented to match the method's level
3. **test_replace_top_level_function** — Replace `helper` (no indentation)
4. **test_replace_updates_index** — After replace, `idx.search_symbols("save")` returns updated line range
5. **test_replace_ambiguous_symbol_errors** — Two files with same symbol name, no `--file` → error
6. **test_replace_with_file_hint** — Disambiguate with `--file`
7. **test_replace_symbol_not_found** — Error message
8. **test_replace_empty_body_errors** — Empty stdin → error

### Tests for `insert-symbol`

1. **test_insert_after_method** — Insert after `User/save`, verify it appears between `save` and `delete`
2. **test_insert_before_method** — Insert before `User/save`
3. **test_insert_after_last_method** — Insert after `User/delete` (last method in class)
4. **test_insert_after_top_level** — Insert after `helper` function
5. **test_insert_preserves_indentation** — Indentation matches anchor
6. **test_insert_adds_blank_line_separator** — Blank line between anchor and new code
7. **test_insert_updates_index** — Index refreshed after insertion

---

## Update the Playbook

After implementing and testing, update these files:

### `src/ii_structure/help_content.yaml`

Add entries for both new commands in the `commands` section following the existing pattern.

### `CLAUDE.md` (generated by `init`)

Find the `CLAUDE_MD_SECTION` variable in `cli.py` (around line 280) and add a new row to the table:

```
| Replace a function/method | Read file + Edit with old_str + new_str | `ii-structure replace-body MyClass/method` (pipe new body via stdin) |
| Insert new code structurally | Read file + figure out line number + Edit | `ii-structure insert-symbol --after MyClass/method` (pipe code via stdin) |
```

Update the line `Edit/Write — modifying files (ii-structure is read-only)` to:
`Edit/Write — line-level edits, non-symbol changes (ii-structure handles symbol-level writes)`

### `src/ii_structure/backends/base.py`

Do NOT add write methods to the `LanguageBackend` Protocol. The write commands operate at the file/line level using index data — they don't need language-specific backends. Keep it simple.

---

## What NOT to Do

- **Do NOT add a `rename` command.** Cross-file renaming requires reference resolution that has edge cases across languages. Out of scope.
- **Do NOT modify signatures.** Only replace bodies or insert new symbols.
- **Do NOT add libcst or rope as dependencies.** The implementation is line-based splicing, not AST transformation.
- **Do NOT modify any existing read commands.** This is purely additive.
- **Do NOT add a `--dry-run` flag.** Agents don't do dry runs. If they want to preview, they use `body` first.
- **Do NOT read from a file path argument.** Always stdin. This keeps the interface consistent and avoids agents having to create temp files.

---

## Definition of Done

1. `ii-structure replace-body User/save` with piped stdin replaces the method and returns structured YAML
2. `ii-structure insert-symbol --after User/save` with piped stdin inserts code and returns structured YAML
3. All tests pass (both new and existing)
4. `ii-structure help` shows both new commands
5. CLAUDE.md section updated to reflect write capabilities
6. No new dependencies added
7. Index auto-refreshes after writes (agent doesn't need to rebuild)
