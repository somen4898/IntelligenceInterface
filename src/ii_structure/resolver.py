import pathlib
from ii_structure.index import Index

try:
    import jedi
except ImportError:
    jedi = None


def find_usages(
    project_root: str,
    name: str,
    index: Index,
    path_scope: str | None = None,
    kind_filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if jedi is None:
        return []

    root = pathlib.Path(project_root)
    project = jedi.Project(path=str(root))

    # Use index to find definition locations
    candidates = index.search_symbols(name)
    if not candidates:
        return []

    all_refs = []
    seen = set()

    for candidate in candidates:
        file_path = root / candidate["file"]
        if not file_path.exists():
            continue

        source = file_path.read_text(encoding="utf-8", errors="replace")
        script = jedi.Script(source, path=str(file_path), project=project)

        try:
            refs = script.get_references(line=candidate["line"], column=0)
        except Exception:
            continue

        for ref in refs:
            ref_path = ref.module_path
            if ref_path is None:
                continue

            try:
                rel = str(pathlib.Path(ref_path).relative_to(root))
            except ValueError:
                continue  # outside project

            if path_scope and not rel.startswith(path_scope):
                continue

            key = (rel, ref.line)
            if key in seen:
                continue
            seen.add(key)

            usage_kind = _classify_reference(ref)
            if kind_filter and usage_kind != kind_filter:
                continue

            context = _get_context_line(root / rel, ref.line)

            all_refs.append({
                "file": rel,
                "line": ref.line,
                "kind": usage_kind,
                "context": context,
            })

            if len(all_refs) >= limit:
                return all_refs

    # If Jedi found nothing, fall back to index definitions themselves
    if not all_refs:
        for candidate in candidates:
            if path_scope and not candidate["file"].startswith(path_scope):
                continue
            usage_kind = "definition"
            if kind_filter and usage_kind != kind_filter:
                continue
            context = _get_context_line(root / candidate["file"], candidate["line"])
            all_refs.append({
                "file": candidate["file"],
                "line": candidate["line"],
                "kind": usage_kind,
                "context": context,
            })
            if len(all_refs) >= limit:
                break

    all_refs.sort(key=lambda r: (r["file"], r["line"]))
    return all_refs


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

    # Multiple candidates — use Jedi to resolve if possible
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


def _classify_reference(ref) -> str:
    desc = ref.description.lower() if ref.description else ""
    if "import" in desc:
        return "import"
    if "def " in desc or "class " in desc:
        return "definition"
    return "reference"


def _get_context_line(file_path: pathlib.Path, line: int) -> str:
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        if 0 < line <= len(lines):
            return lines[line - 1].strip()
    except Exception:
        pass
    return ""
