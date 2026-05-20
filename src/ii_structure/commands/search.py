from ii_structure.index import Index


def execute(idx: Index, query: str, limit: int = 20) -> list[dict]:
    """Ranked search over symbol names and docstrings.

    Scores matches by: exact name (100), prefix (80), substring in name (60),
    or substring in docstring (20). Returns up to `limit` results sorted by
    relevance, then file and line.
    """
    query_lower = query.lower()
    scored = []

    for rel_path, file_data in idx.files.items():
        for symbol in file_data["symbols"]:
            score = _score_match(symbol, query_lower)
            if score > 0:
                scored.append((score, {
                    "file": rel_path,
                    "name": symbol["name"],
                    "kind": symbol["kind"],
                    "line": symbol["line"],
                    "signature": symbol["signature"],
                    "docstring": symbol.get("docstring"),
                    "parent": symbol.get("parent"),
                }))

    scored.sort(key=lambda x: (-x[0], x[1]["file"], x[1]["line"]))
    return [item for _, item in scored[:limit]]


def _score_match(symbol: dict, query_lower: str) -> int:
    name = symbol["name"].lower()
    docstring = (symbol.get("docstring") or "").lower()

    # Exact name match
    if name == query_lower:
        return 100

    # Prefix match
    if name.startswith(query_lower):
        return 80

    # Substring in name
    if query_lower in name:
        return 60

    # Docstring match
    if query_lower in docstring:
        return 20

    return 0
