from ii_structure.index import Index


def execute(idx: Index, project_root: str, name: str, max_depth: int = 3,
            file_hint: str | None = None) -> dict:
    """Find the blast radius of changing a symbol — what's affected?"""
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

    result = idx.graph.get_impact_radius(qn, max_depth=max_depth)

    affected = []
    for node in result["impacted_nodes"]:
        affected.append({
            "symbol": node["name"],
            "file": node["file_path"],
            "line": node.get("line_start"),
            "depth": node.get("depth", 0),
            "kind": node["kind"],
        })

    tests = idx.graph.get_transitive_tests(qn)
    test_names = [{"name": t["name"], "file": t["file_path"], "indirect": t.get("indirect", False)} for t in tests]

    return {
        "symbol": name,
        "file": file_path,
        "affected": affected,
        "affected_files": result["impacted_files"],
        "tests": test_names,
        "total_affected": result["total_impacted"],
    }
