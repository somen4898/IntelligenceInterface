import os
from ii_structure.index import Index


def execute(
    idx: Index,
    project_root: str,
    name: str,
    path_scope: str | None = None,
    kind_filter: str | None = None,
    limit: int = 50,
    include_tests: bool = True,
) -> list[dict]:
    """Find all references to a symbol via pre-computed edges."""
    candidates = idx.search_symbols(name)
    if not candidates:
        return []

    # Build qualified name from first candidate
    candidate = candidates[0]
    file_path = candidate["file"]
    parent = candidate.get("parent")
    if parent:
        qn = f"{file_path}::{parent}.{candidate['name']}"
    else:
        qn = f"{file_path}::{candidate['name']}"

    # Query edges -- who calls this symbol?
    edges = idx.graph.get_edges_by_target(qn)

    # Also try bare name match (for unresolved edges)
    bare_edges = idx.graph.get_edges_by_target(candidate["name"])

    all_edges = edges + [e for e in bare_edges if e not in edges]

    results = []
    seen = set()
    for edge in all_edges:
        if edge["kind"] != "CALLS" and edge["kind"] != "TESTED_BY":
            continue

        source_qn = edge["source_qualified"]
        if source_qn in seen:
            continue
        seen.add(source_qn)

        # Normalize file_path to relative (edges may store absolute paths)
        source_file = edge["file_path"]
        if os.path.isabs(source_file) and project_root:
            try:
                source_file = os.path.relpath(source_file, project_root)
            except ValueError:
                pass

        # Apply filters
        if path_scope and not source_file.startswith(path_scope):
            continue

        is_test = (
            source_file.startswith("test_")
            or "/test_" in source_file
            or source_file.startswith("tests/")
        )
        if not include_tests and is_test:
            continue

        kind = "reference"
        if edge["kind"] == "TESTED_BY":
            kind = "test"

        # Try to get source node info for context.
        # Node qualified names use relative paths, so normalize source_qn.
        context = ""
        node_qn = source_qn
        if os.path.isabs(source_qn.split("::")[0]) and project_root:
            try:
                rel_file = os.path.relpath(source_qn.split("::")[0], project_root)
                parts = source_qn.split("::", 1)
                node_qn = f"{rel_file}::{parts[1]}" if len(parts) > 1 else rel_file
            except ValueError:
                pass

        source_node = idx.graph.get_node(node_qn)
        if source_node:
            context = source_node.get("signature", "") or ""

        results.append({
            "file": source_file,
            "line": edge["line"],
            "kind": kind,
            "context": context,
        })

    if kind_filter:
        results = [r for r in results if r["kind"] == kind_filter]

    return results[:limit]
