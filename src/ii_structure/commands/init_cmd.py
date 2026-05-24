"""Init command — adds ii-structure instructions to CLAUDE.md."""
import click


CLAUDE_MD_SECTION = """\

# ii-structure — MANDATORY for Code Navigation, Editing, and Analysis

You have `ii-structure` installed. It provides structural code navigation, symbol-level editing, and impact analysis. Uses 3-15x fewer tokens than Read/Grep/Glob.

## HARD RULES — Violations Waste Tokens

1. **NEVER read a source file to find a function.** Use `ii-structure body Symbol/name`. Reading a 500-line file to find a 10-line function wastes 490 lines of tokens.
2. **NEVER grep for a symbol definition.** Use `ii-structure locate Name` or `ii-structure search query`. Grep returns noise — ii-structure returns only definitions.
3. **NEVER read a whole file to understand its structure.** Use `ii-structure outline file.py --depth full`. Returns the skeleton in ~100 tokens instead of ~2000.
4. **NEVER use Read + Edit to rewrite a function.** Use `ii-structure body Name` (get hash) → `ii-structure replace-body Name --expect-hash <hash>`.
5. **ALWAYS run `ii-structure files --summary`** on any new or unfamiliar project.
6. **ALWAYS run `ii-structure blast-radius Name`** before refactoring to understand impact.
7. **ALWAYS run `ii-structure overview`** as your FIRST command on any new project — cheaper than files --summary.

## Decision Tree — What Tool To Use

```
I need to...
├── READ code
│   ├── Know the symbol name? → ii-structure body Symbol/name
│   ├── Know the file? → ii-structure outline file.py
│   ├── Don't know the name? → ii-structure search <query>
│   └── Need a string literal or regex? → Grep (ONLY case)
│
├── FIND something
│   ├── Where is it defined? → ii-structure locate Name
│   ├── Who calls it? → ii-structure usages Name
│   ├── What depends on this file? → ii-structure imports file.py
│   └── Looking for a filename? → Glob (ONLY case)
│
├── ANALYZE impact
│   ├── What breaks if I change X? → ii-structure blast-radius X
│   ├── Is there dead code? → ii-structure dead-code [--file FILE]
│   └── Is X tested? → ii-structure test-coverage X
│
├── WRITE code
│   ├── Rewrite a function/method?
│   │   1. ii-structure body Name → get content_hash
│   │   2. echo 'new code' | ii-structure replace-body Name --expect-hash <hash>
│   ├── Add new code next to a symbol?
│   │   1. ii-structure body AnchorName → get content_hash
│   │   2. echo 'new code' | ii-structure insert-symbol --after AnchorName --expect-hash <hash>
│   └── Non-symbol edit? → Edit tool
│
└── UNDERSTAND the project
    ├── Quick overview? → ii-structure overview
    ├── Detailed file list? → ii-structure files --summary --no-tests --no-private
    ├── File structure? → ii-structure outline file.py --depth full
    └── Dependencies? → ii-structure imports file.py
```

## When Native Tools ARE Correct

- `Glob` — finding files by name pattern (NOT for finding code)
- `Grep` — string literals, TODOs, comments, regex (NOT for finding symbols)
- `Read` — non-code files (config, docs) or specific line ranges you already know
- `Edit/Write` — non-symbol edits (string changes, config)

## Key Flags

- `--expect-hash` on write commands — content_hash from `body`, prevents stale writes
- `--depth N` on `blast-radius` — traversal depth (default 3)
- `--no-tests` on `usages` — exclude test files when exploring
- `--depth full` on `outline` — include methods inside classes
- `--kind` on `locate`/`outline` — filter by type
- `--match substring` on `locate` — partial name matching
- `--file` on any command — disambiguate when symbols share names

## Workflow

```
New project → files --summary → outline → locate/body → blast-radius before refactoring → replace-body to edit → usages to verify
```
"""

MARKER = "# ii-structure"


def register(cli_group):
    """Register the init command on the given CLI group."""

    @cli_group.command()
    @click.pass_context
    def init(ctx):
        """Add ii-structure instructions to CLAUDE.md for this project."""
        import importlib.util
        import pathlib
        import shutil

        root = ctx.obj.get("root")
        if root is None:
            root = pathlib.Path.cwd()

        claude_md = root / "CLAUDE.md"

        if claude_md.exists():
            existing = claude_md.read_text()
            if MARKER in existing:
                click.echo("ii-structure section already exists in CLAUDE.md — skipping.")
                return
            # Append to existing file
            with open(claude_md, "a") as f:
                f.write(CLAUDE_MD_SECTION)
            click.echo(f"Appended ii-structure instructions to {claude_md}")
        else:
            claude_md.write_text(CLAUDE_MD_SECTION.lstrip())
            click.echo(f"Created {claude_md} with ii-structure instructions")

        # Detect languages and language servers
        click.echo("")
        click.echo("Languages detected:")

        # Python
        has_py = any(root.rglob("*.py"))
        has_jedi = importlib.util.find_spec("jedi") is not None
        if has_py:
            if has_jedi:
                click.echo("  Python (.py):     \u2713 full support (Jedi installed)")
            else:
                click.echo("  Python (.py):     \u26a0 structural only \u2014 install jedi for type-resolved usages:")
                click.echo("                      pip install jedi")

        # Go
        has_go = any(root.rglob("*.go"))
        if has_go:
            if shutil.which("gopls"):
                click.echo("  Go (.go):         \u2713 full support (gopls available)")
            else:
                click.echo("  Go (.go):         \u26a0 structural only \u2014 install gopls for type-resolved usages:")
                click.echo("                      go install golang.org/x/tools/gopls@latest")

        # TypeScript
        has_ts = any(root.rglob("*.ts")) or any(root.rglob("*.tsx"))
        if has_ts:
            if shutil.which("typescript-language-server"):
                click.echo("  TypeScript (.ts): \u2713 full support (tsserver available)")
            else:
                click.echo("  TypeScript (.ts): \u26a0 structural only \u2014 install tsserver for type-resolved usages:")
                click.echo("                      npm install -g typescript-language-server typescript")

        click.echo("")
        click.echo("Your AI agent will now use ii-structure automatically.")
