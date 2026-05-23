from ii_structure.index import Index


def execute(idx: Index, project_root: str, name: str, max_depth: int = 2,
            file_hint: str | None = None) -> dict:
    """Find structural test coverage for a symbol."""
    candidates = idx.search_symbols(name)
    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]
    if not candidates:
        raise ValueError(f"Symbol '{name}' not found in index")

    candidate = candidates[0]
    file_path = candidate["file"]
    parent = candidate.get("parent")
    if parent:
        qn = f"{file_path}::{parent}.{candidate['name']}"
    else:
        qn = f"{file_path}::{candidate['name']}"

    tests = idx.graph.get_transitive_tests(qn, max_depth=max_depth)

    return {
        "symbol": name,
        "file": file_path,
        "tests": [{
            "name": t["name"],
            "file": t["file_path"],
            "indirect": t.get("indirect", False),
        } for t in tests],
        "total_tests": len(tests),
        "covered": len(tests) > 0,
    }
