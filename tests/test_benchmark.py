import pathlib
import json
import pytest
from benchmarks.runner import (
    load_queries,
    run_query,
    run_benchmark,
    evaluate_rubric,
    format_report,
    save_baseline,
    compare_baselines,
)


@pytest.fixture
def project_root():
    return str(pathlib.Path(__file__).parent.parent)


@pytest.fixture
def queries_dir():
    return pathlib.Path(__file__).parent.parent / "benchmarks" / "queries"


def test_load_queries(queries_dir):
    queries = load_queries(queries_dir)
    assert len(queries) >= 10
    assert all("id" in q for q in queries)
    assert all("rubric" in q for q in queries)


def test_run_single_query(project_root, queries_dir):
    queries = load_queries(queries_dir)
    result = run_query(queries[0], project_root)
    assert "id" in result
    assert "output_bytes" in result
    assert "correct" in result
    assert result["output_bytes"] > 0


def test_evaluate_exact_match():
    rubric = {"type": "exact-match", "expected": {"name": "User", "kind": "class"}}
    output = 'ok: true\ncommand: locate\nresult:\n- name: User\n  kind: class\n  file: models.py\n'
    assert evaluate_rubric(rubric, [output]) is True


def test_evaluate_must_contain():
    rubric = {"type": "must-contain", "expected_items": ["foo", "bar"]}
    assert evaluate_rubric(rubric, ["foo bar baz"]) is True
    assert evaluate_rubric(rubric, ["foo only"]) is False


def test_evaluate_min_count():
    rubric = {"type": "min-count", "min_results": 2}
    output = "ok: true\ncommand: usages\nresult:\n- file: a.py\n  line: 1\n- file: b.py\n  line: 2\n"
    assert evaluate_rubric(rubric, [output]) is True


def test_format_report(project_root, queries_dir):
    queries = load_queries(queries_dir)
    result = run_query(queries[0], project_root)
    report = format_report([result])
    assert "ID" in report
    assert queries[0]["id"] in report


def test_save_and_compare(project_root, queries_dir, tmp_path):
    results = [{"id": "test-1", "archetype": "find-known", "description": "test",
                "output_bytes": 100, "commands": 1, "wall_clock_s": 0.1, "correct": True}]
    path = save_baseline(results, tmp_path, "test")
    assert path.exists()

    baseline = json.loads(path.read_text())
    report = compare_baselines(results, baseline)
    assert "Regressions: 0" in report


def test_full_benchmark_run(project_root, queries_dir):
    """Integration: run all queries against the actual project."""
    results = run_benchmark(project_root, queries_dir)
    assert len(results) >= 10
    correct = sum(1 for r in results if r["correct"])
    # At least 80% should pass
    assert correct >= len(results) * 0.8, f"Only {correct}/{len(results)} passed"
