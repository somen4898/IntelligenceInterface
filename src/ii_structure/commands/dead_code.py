from ii_structure.index import Index


def execute(idx: Index, file_hint: str | None = None) -> list[dict]:
    """Find symbols with no incoming call edges (potentially dead code)."""
    dead = idx.graph.get_dead_symbols(file_path=file_hint)
    return [{
        "symbol": d["name"],
        "file": d["file_path"],
        "line": d.get("line_start"),
        "kind": d["kind"],
        "parent": d.get("parent_name"),
    } for d in dead]
