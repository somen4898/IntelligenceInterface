"""Benchmark runner for ii-structure."""

import json
import pathlib
import subprocess
import sys
import time
import yaml
from typing import Any


def load_queries(queries_dir: pathlib.Path) -> list[dict]:
    queries = []
    for f in sorted(queries_dir.glob("*.yaml")):
        queries.append(yaml.safe_load(f.read_text()))
    return queries


def run_query(query: dict, project_root: str) -> dict:
    """Run a single benchmark query and measure results."""
    total_bytes = 0
    total_time = 0.0
    all_outputs = []

    for cmd_str in query["commands"]:
        args = cmd_str.split()
        full_cmd = [sys.executable, "-m", "ii_structure.cli", "--project", project_root] + args

        start = time.monotonic()
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
        )
        elapsed = time.monotonic() - start

        output = result.stdout
        total_bytes += len(output.encode("utf-8"))
        total_time += elapsed
        all_outputs.append(output)

    # Evaluate correctness
    correct = evaluate_rubric(query["rubric"], all_outputs)

    return {
        "id": query["id"],
        "archetype": query["archetype"],
        "description": query["description"],
        "output_bytes": total_bytes,
        "commands": len(query["commands"]),
        "wall_clock_s": round(total_time, 3),
        "correct": correct,
    }


def evaluate_rubric(rubric: dict, outputs: list[str]) -> bool:
    combined = "\n".join(outputs)
    rubric_type = rubric["type"]

    if rubric_type == "exact-match":
        try:
            parsed = yaml.safe_load(outputs[0])
            if not parsed.get("ok"):
                return False
            results = parsed.get("result", [])
            if isinstance(results, dict):
                results = [results]
            expected = rubric["expected"]
            for result in results:
                match = all(
                    result.get(k) == v
                    for k, v in expected.items()
                )
                if match:
                    return True
            return False
        except Exception:
            return False

    elif rubric_type == "must-contain":
        for item in rubric["expected_items"]:
            if item not in combined:
                return False
        return True

    elif rubric_type == "must-contain-any":
        for item in rubric["expected_items"]:
            if item in combined:
                return True
        return False

    elif rubric_type == "min-count":
        try:
            parsed = yaml.safe_load(outputs[0])
            results = parsed.get("result", [])
            if isinstance(results, list):
                return len(results) >= rubric["min_results"]
            return False
        except Exception:
            return False

    return False


def run_benchmark(project_root: str, queries_dir: pathlib.Path) -> list[dict]:
    queries = load_queries(queries_dir)
    results = []
    for query in queries:
        result = run_query(query, project_root)
        results.append(result)
    return results


def format_report(results: list[dict]) -> str:
    lines = []
    lines.append(f"{'ID':<20} {'Arch':<15} {'Bytes':>8} {'Cmds':>5} {'Time':>8} {'Pass':>5}")
    lines.append("-" * 65)

    total_bytes = 0
    total_correct = 0

    for r in results:
        mark = "✓" if r["correct"] else "✗"
        lines.append(
            f"{r['id']:<20} {r['archetype']:<15} {r['output_bytes']:>8} "
            f"{r['commands']:>5} {r['wall_clock_s']:>7.2f}s {mark:>5}"
        )
        total_bytes += r["output_bytes"]
        if r["correct"]:
            total_correct += 1

    lines.append("-" * 65)
    lines.append(f"Total: {len(results)} queries, {total_correct}/{len(results)} correct, {total_bytes} bytes")

    return "\n".join(lines)


def save_baseline(results: list[dict], baselines_dir: pathlib.Path, name: str = "current") -> pathlib.Path:
    baselines_dir.mkdir(parents=True, exist_ok=True)
    path = baselines_dir / f"{name}.json"
    path.write_text(json.dumps(results, indent=2))
    return path


def compare_baselines(current: list[dict], baseline: list[dict]) -> str:
    lines = []
    baseline_map = {r["id"]: r for r in baseline}

    lines.append(f"{'ID':<20} {'Bytes Δ':>10} {'Correct Δ':>12}")
    lines.append("-" * 45)

    regressions = 0
    for r in current:
        bid = r["id"]
        if bid in baseline_map:
            b = baseline_map[bid]
            byte_delta = r["output_bytes"] - b["output_bytes"]
            byte_str = f"{byte_delta:+d}"
            if b["correct"] and not r["correct"]:
                correct_str = "REGRESSION"
                regressions += 1
            elif not b["correct"] and r["correct"]:
                correct_str = "FIXED"
            else:
                correct_str = "same"
            lines.append(f"{bid:<20} {byte_str:>10} {correct_str:>12}")

    lines.append(f"\nRegressions: {regressions}")
    return "\n".join(lines)
