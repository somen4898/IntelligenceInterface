import yaml
from ii_structure.output import format_success, format_error


def test_format_success_basic():
    result = format_success("locate", [{"file": "a.py", "line": 1}])
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is True
    assert parsed["command"] == "locate"
    assert parsed["result"] == [{"file": "a.py", "line": 1}]


def test_format_success_empty_result():
    result = format_success("files", [])
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is True
    assert parsed["result"] == []


def test_format_error_basic():
    result = format_error("locate", "Symbol not found")
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is False
    assert parsed["command"] == "locate"
    assert parsed["error"] == "Symbol not found"
    assert "suggestion" not in parsed


def test_format_error_with_suggestion():
    result = format_error("locate", "Not found", suggestion="Try 'User'")
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is False
    assert parsed["suggestion"] == "Try 'User'"


def test_format_success_truncated():
    items = [{"name": f"sym{i}"} for i in range(30)]
    result = format_success("search", items, total=100, limit=30)
    parsed = yaml.safe_load(result)
    assert parsed["ok"] is True
    assert parsed["total"] == 100
    assert parsed["truncated"] is True
    assert parsed["limit"] == 30
    assert len(parsed["result"]) == 30


def test_output_is_valid_yaml():
    result = format_success("outline", {"file": "test.py", "symbols": []})
    parsed = yaml.safe_load(result)
    assert isinstance(parsed, dict)
