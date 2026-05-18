import yaml
from typing import Any


def format_success(
    command: str,
    result: Any,
    total: int | None = None,
    limit: int | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "ok": True,
        "command": command,
        "result": result,
    }
    if total is not None and limit is not None:
        envelope["total"] = total
        envelope["truncated"] = True
        envelope["limit"] = limit
    return yaml.dump(envelope, default_flow_style=False, sort_keys=False)


def format_error(
    command: str,
    error: str,
    suggestion: str | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "ok": False,
        "command": command,
        "error": error,
    }
    if suggestion is not None:
        envelope["suggestion"] = suggestion
    return yaml.dump(envelope, default_flow_style=False, sort_keys=False)
