"""Benchmark commands for ii-structure."""
import json
import pathlib
import sys

import click
import yaml

from ii_structure.output import format_error


def register(cli_group):
    """Register the benchmark command group on the given CLI group."""

    @cli_group.group()
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
