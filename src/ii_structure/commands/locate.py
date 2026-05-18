from ii_structure.index import Index


def execute(
    idx: Index,
    name: str,
    kind: str | None = None,
    file: str | None = None,
    match: str = "exact",
) -> list[dict]:
    anchored = name.startswith("/")
    clean_name = name.lstrip("/")
    parts = clean_name.split("/")

    results = []

    for rel_path, file_data in idx.files.items():
        if file is not None and rel_path != file:
            continue

        for symbol in file_data["symbols"]:
            if not _matches(symbol, parts, match, anchored):
                continue
            if kind is not None and symbol["kind"] != kind:
                continue

            results.append({
                "file": rel_path,
                "line": symbol["line"],
                "kind": symbol["kind"],
                "name": symbol["name"],
                "signature": symbol["signature"],
                "docstring": symbol.get("docstring"),
                "parent": symbol.get("parent"),
            })

    return results


def _matches(
    symbol: dict,
    parts: list[str],
    match: str,
    anchored: bool,
) -> bool:
    if len(parts) == 1:
        target = parts[0]
        if anchored and symbol.get("parent") is not None:
            return False
        if match == "substring":
            return target.lower() in symbol["name"].lower()
        return symbol["name"] == target

    # Name path: e.g. ["User", "save"]
    if symbol["name"] != parts[-1]:
        return False
    if symbol.get("parent") is None:
        return False

    parent_parts = symbol["parent"].split("/")
    expected_parents = parts[:-1]

    if anchored:
        return parent_parts == expected_parents
    # Non-anchored: expected parents must be a suffix of actual parents
    if len(expected_parents) > len(parent_parts):
        return False
    return parent_parts[-len(expected_parents):] == expected_parents
