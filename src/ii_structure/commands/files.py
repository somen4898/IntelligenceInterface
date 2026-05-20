import fnmatch
from ii_structure.index import Index


def execute(
    idx: Index,
    glob_pattern: str | None = None,
    path_prefix: str | None = None,
    summary: bool = False,
) -> list:
    """List all indexed source files, optionally filtered by glob or path prefix.

    When summary=True, includes top-level symbol signatures for each file,
    giving a quick project map without reading full outlines.
    """
    files = sorted(idx.files.keys())

    if path_prefix:
        files = [f for f in files if f.startswith(path_prefix)]

    if glob_pattern:
        files = [f for f in files if fnmatch.fnmatch(f, glob_pattern)]

    if not summary:
        return files

    result = []
    for f in files:
        file_data = idx.files[f]
        # Top-level symbols only (no methods — those are discoverable via outline)
        top_symbols = [
            s for s in file_data["symbols"]
            if s.get("parent") is None
        ]
        signatures = [s["signature"] for s in top_symbols]

        entry = {"file": f, "symbols": signatures}
        result.append(entry)

    return result
