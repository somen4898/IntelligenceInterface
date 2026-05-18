from ii_structure.index import Index


def execute(
    idx: Index,
    file: str,
    depth: str = "top",
    kind: str | None = None,
) -> dict:
    if file not in idx.files:
        raise FileNotFoundError(f"File '{file}' not found in index")

    file_data = idx.files[file]
    symbols = file_data["symbols"]

    if depth == "top":
        symbols = [s for s in symbols if s.get("parent") is None]

    if kind is not None:
        symbols = [s for s in symbols if s["kind"] == kind]

    # Build clean output — strip internal fields
    clean_symbols = []
    for s in symbols:
        entry = {
            "name": s["name"],
            "kind": s["kind"],
            "line": s["line"],
            "signature": s["signature"],
        }
        if s.get("docstring"):
            entry["docstring"] = s["docstring"]
        if s.get("children"):
            entry["children"] = s["children"]
        if s.get("decorators"):
            entry["decorators"] = s["decorators"]
        clean_symbols.append(entry)

    return {
        "file": file,
        "symbols": clean_symbols,
        "imports": file_data["imports"],
    }
