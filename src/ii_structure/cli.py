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
@click.option("--glob", "glob_pattern", default=None, help="Filter by glob pattern")
@click.option("--path", "path_prefix", default=None, help="Filter by path prefix")
@click.pass_context
def files(ctx, glob_pattern, path_prefix):
    """List all indexed Python files."""
    try:
        idx = _get_index(ctx)
        from ii_structure.commands.files import execute
        results = execute(idx, glob_pattern=glob_pattern, path_prefix=path_prefix)
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
@click.pass_context
def usages(ctx, name, path_scope, kind, limit):
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


def main():
    cli()


if __name__ == "__main__":
    main()
