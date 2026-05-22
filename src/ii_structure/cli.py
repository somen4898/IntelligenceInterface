import json
import pathlib
import sys

import click
import yaml

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
@click.option("--glob", "glob_pattern", default=None, help="Filter by glob pattern")
@click.option("--path", "path_prefix", default=None, help="Filter by path prefix")
@click.option("--summary", is_flag=True, default=False, help="Include top-level symbol signatures per file")
@click.pass_context
def files(ctx, glob_pattern, path_prefix, summary):
    """List all indexed source files."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.files import execute
        results = execute(idx, glob_pattern=glob_pattern, path_prefix=path_prefix, summary=summary)
        click.echo(format_success("files", results))
    except Exception as e:
        click.echo(format_error("files", str(e)))
        sys.exit(1)


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
        sys.exit(1)
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


@cli.command()
@click.argument("name")
@click.option("--path", "path_scope", default=None, help="Restrict to directory subtree")
@click.option("--kind", type=click.Choice(["call", "import", "assignment", "reference", "definition"]), default=None)
@click.option("--limit", type=int, default=50, help="Max results")
@click.option("--no-tests", is_flag=True, default=False, help="Exclude test files from results")
@click.pass_context
def usages(ctx, name, path_scope, kind, limit, no_tests):
    """Find all references to a symbol, resolved by type."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.usages import execute
        results = execute(
            idx=idx,
            project_root=str(ctx.obj["root"]),
            name=name,
            path_scope=path_scope,
            kind_filter=kind,
            limit=limit,
            include_tests=not no_tests,
        )
        total = len(results)
        if total >= limit:
            click.echo(format_success("usages", results, total=total, limit=limit))
        else:
            click.echo(format_success("usages", results))
    except Exception as e:
        click.echo(format_error("usages", str(e)))
        sys.exit(1)


@cli.command()
@click.argument("name")
@click.option("--file", "file_hint", default=None, help="Disambiguate by file")
@click.pass_context
def body(ctx, name, file_hint):
    """Get the full source body of a symbol."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.body import execute
        result = execute(
            idx=idx,
            project_root=str(ctx.obj["root"]),
            name=name,
            file_hint=file_hint,
        )
        if result is None:
            click.echo(format_error("body", f"Symbol '{name}' not found",
                       suggestion=f"Try: ii-structure locate {name}"))
            sys.exit(1)
        else:
            click.echo(format_success("body", result))
    except Exception as e:
        click.echo(format_error("body", str(e)))
        sys.exit(1)


@cli.command()
@click.argument("query")
@click.option("--limit", type=int, default=20, help="Max results")
@click.pass_context
def search(ctx, query, limit):
    """Search symbol names and docstrings."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.search import execute
        results = execute(idx, query=query, limit=limit)
        click.echo(format_success("search", results))
    except Exception as e:
        click.echo(format_error("search", str(e)))
        sys.exit(1)


@cli.command(name="help")
@click.argument("command", required=False, default=None)
@click.pass_context
def help_cmd(ctx, command):
    """Show command documentation for agents."""
    try:
        from ii_structure.commands.help import execute
        result = execute(command=command)
        if result is None:
            click.echo(format_error("help", f"Unknown command: {command}",
                       suggestion="Run 'ii-structure help' for the full command list."))
            sys.exit(1)
        else:
            click.echo(format_success("help", result))
    except Exception as e:
        click.echo(format_error("help", str(e)))
        sys.exit(1)


@cli.command("replace-body")
@click.argument("name")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.option("--expect-hash", default=None, help="Reject if file content hash doesn't match (from body command)")
@click.pass_context
def replace_body(ctx, name, file_hint, expect_hash):
    """Replace the full source of a symbol with new code from stdin."""
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
                        new_body=new_body, file_hint=file_hint,
                        expect_hash=expect_hash)
        click.echo(format_success("replace-body", result))
    except Exception as e:
        click.echo(format_error("replace-body", str(e)))
        sys.exit(1)


@cli.command("insert-symbol")
@click.option("--after", "after_symbol", default=None, help="Insert after this symbol")
@click.option("--before", "before_symbol", default=None, help="Insert before this symbol")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.option("--expect-hash", default=None, help="Reject if file content hash doesn't match (from body command)")
@click.pass_context
def insert_symbol(ctx, after_symbol, before_symbol, file_hint, expect_hash):
    """Insert new code before or after an existing symbol."""
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
                        position=position, new_code=new_code, file_hint=file_hint,
                        expect_hash=expect_hash)
        click.echo(format_success("insert-symbol", result))
    except Exception as e:
        click.echo(format_error("insert-symbol", str(e)))
        sys.exit(1)


@cli.command("blast-radius")
@click.argument("name")
@click.option("--depth", type=int, default=3, help="Max traversal depth")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.pass_context
def blast_radius(ctx, name, depth, file_hint):
    """Show what's affected if a symbol changes."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.blast_radius import execute
        result = execute(idx=idx, project_root=str(ctx.obj["root"]),
                        name=name, max_depth=depth, file_hint=file_hint)
        click.echo(format_success("blast-radius", result))
    except Exception as e:
        click.echo(format_error("blast-radius", str(e)))
        sys.exit(1)


@cli.command("dead-code")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.pass_context
def dead_code(ctx, file_hint):
    """Find symbols with no callers (potentially dead code)."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.dead_code import execute
        result = execute(idx=idx, file_hint=file_hint)
        click.echo(format_success("dead-code", result))
    except Exception as e:
        click.echo(format_error("dead-code", str(e)))
        sys.exit(1)


@cli.command("test-coverage")
@click.argument("name")
@click.option("--depth", type=int, default=2, help="Max depth for transitive test discovery")
@click.option("--file", "file_hint", default=None, help="Restrict to a specific file")
@click.pass_context
def test_coverage(ctx, name, depth, file_hint):
    """Show structural test coverage for a symbol."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.test_coverage import execute
        result = execute(idx=idx, project_root=str(ctx.obj["root"]),
                        name=name, max_depth=depth, file_hint=file_hint)
        click.echo(format_success("test-coverage", result))
    except Exception as e:
        click.echo(format_error("test-coverage", str(e)))
        sys.exit(1)


@cli.command(name="imports")
@click.argument("file")
@click.option("--depth", type=int, default=1, help="Hop distance")
@click.option("--include-external", is_flag=True, default=False, help="Include third-party packages")
@click.pass_context
def imports_cmd(ctx, file, depth, include_external):
    """What a file imports and what imports it."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.imports import execute
        result = execute(idx, file=file, depth=depth, include_external=include_external)
        click.echo(format_success("imports", result))
    except FileNotFoundError as e:
        click.echo(format_error("imports", str(e)))
        sys.exit(1)
    except Exception as e:
        click.echo(format_error("imports", str(e)))
        sys.exit(1)


@cli.group()
def benchmark():
    """Run benchmarks."""
    pass


@benchmark.command(name="run")
@click.option("--query", default=None, help="Run a single query by ID")
@click.pass_context
def benchmark_run(ctx, query):
    """Run benchmark queries and report results."""
    root = ctx.obj.get("root")
    if root is None:
        # For benchmark, default to cwd
        root = pathlib.Path.cwd()

    # Find benchmarks directory
    benchmarks_dir = root / "benchmarks"
    queries_dir = benchmarks_dir / "queries"

    if not queries_dir.exists():
        click.echo(format_error("benchmark", f"Queries directory not found: {queries_dir}"))
        sys.exit(1)

    # Ensure benchmarks package is importable from project root
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from benchmarks.runner import run_benchmark, format_report, save_baseline, load_queries, run_query

    if query:
        queries = load_queries(queries_dir)
        matched = [q for q in queries if q["id"] == query]
        if not matched:
            click.echo(format_error("benchmark", f"Query '{query}' not found"))
            sys.exit(1)
        result = run_query(matched[0], str(root))
        click.echo(yaml.dump(result, default_flow_style=False, sort_keys=False))
    else:
        results = run_benchmark(str(root), queries_dir)
        report = format_report(results)
        click.echo(report)

        baselines_dir = benchmarks_dir / "baselines"
        save_baseline(results, baselines_dir)
        click.echo(f"\nBaseline saved to {baselines_dir / 'current.json'}")


@benchmark.command(name="compare")
@click.argument("baseline_file", type=click.Path(exists=True))
@click.pass_context
def benchmark_compare(ctx, baseline_file):
    """Compare current results against a baseline."""
    root = ctx.obj.get("root")
    if root is None:
        root = pathlib.Path.cwd()

    benchmarks_dir = root / "benchmarks"
    queries_dir = benchmarks_dir / "queries"

    # Ensure benchmarks package is importable from project root
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from benchmarks.runner import run_benchmark, compare_baselines

    current = run_benchmark(str(root), queries_dir)
    baseline = json.loads(pathlib.Path(baseline_file).read_text())

    report = compare_baselines(current, baseline)
    click.echo(report)


CLAUDE_MD_SECTION = """\

# ii-structure — MANDATORY for Code Navigation, Editing, and Analysis

You have `ii-structure` installed. It provides structural code navigation, symbol-level editing, and impact analysis. Uses 3-15x fewer tokens than Read/Grep/Glob.

## HARD RULES — Violations Waste Tokens

1. **NEVER read a source file to find a function.** Use `ii-structure body Symbol/name`.
2. **NEVER grep for a symbol definition.** Use `ii-structure locate Name` or `ii-structure search query`.
3. **NEVER read a whole file to understand its structure.** Use `ii-structure outline file.py --depth full`.
4. **NEVER use Read + Edit to rewrite a function.** Use `ii-structure body Name` (get hash) → `ii-structure replace-body Name --expect-hash <hash>`.
5. **ALWAYS run `ii-structure files --summary`** on any new or unfamiliar project.
6. **ALWAYS run `ii-structure blast-radius Name`** before refactoring to understand impact.

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
    ├── Project overview? → ii-structure files --summary
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
- `--file` on any command — disambiguate when symbols share names

## Workflow

```
New project → files --summary → outline → locate/body → blast-radius before refactoring → replace-body to edit → usages to verify
```
"""

MARKER = "# ii-structure"


@cli.command()
@click.pass_context
def init(ctx):
    """Add ii-structure instructions to CLAUDE.md for this project."""
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
    has_jedi = True
    try:
        import jedi
    except ImportError:
        has_jedi = False
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


def main():
    cli()


if __name__ == "__main__":
    main()
