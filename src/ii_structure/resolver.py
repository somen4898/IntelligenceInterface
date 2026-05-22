import pathlib
from ii_structure.index import Index

try:
    import jedi
except ImportError:
    jedi = None


def get_definition_source(
    project_root: str,
    name: str,
    index: Index,
    file_hint: str | None = None,
) -> dict | None:
    root = pathlib.Path(project_root)

    candidates = index.search_symbols(name)
    if not candidates:
        return None

    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]
        if not candidates:
            return None

    # If only one candidate, read directly (skip Jedi)
    if len(candidates) == 1:
        return _read_symbol_source(root, candidates[0])

    # Multiple candidates -- use Jedi to resolve if possible
    if jedi is not None:
        project = jedi.Project(path=str(root))
        for candidate in candidates:
            file_path = root / candidate["file"]
            if not file_path.exists():
                continue
            source = file_path.read_text(encoding="utf-8", errors="replace")
            script = jedi.Script(source, path=str(file_path), project=project)
            try:
                defs = script.goto(line=candidate["line"], column=len("def "))
                if defs:
                    return _read_symbol_source(root, candidate)
            except Exception:
                continue

    # Fallback: return first candidate
    return _read_symbol_source(root, candidates[0])


def _read_symbol_source(root: pathlib.Path, candidate: dict) -> dict:
    file_path = root / candidate["file"]
    source = file_path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()

    start = candidate["line"] - 1  # 0-indexed
    end = candidate.get("end_line", candidate["line"])  # 1-indexed

    body = "\n".join(lines[start:end])

    return {
        "file": candidate["file"],
        "line": candidate["line"],
        "end_line": end,
        "name": candidate["name"],
        "kind": candidate["kind"],
        "source": body,
    }
