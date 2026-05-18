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


def main():
    cli()


if __name__ == "__main__":
    main()
