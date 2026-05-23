import fnmatch
from ii_structure.index import Index


def execute(
    idx: Index,
    glob_pattern: str | None = None,
    path_prefix: str | None = None,
    summary: bool = False,
    no_tests: bool = False,
    no_private: bool = False,
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

    # Test file patterns
    test_patterns = {"test_", "tests/", "test/", "_test.", ".test.", ".spec.", "conftest.py"}

    result = []
    for f in files:
        # Skip test files if requested
        if no_tests:
            name = f.rsplit("/", 1)[-1] if "/" in f else f
            if any(p in f or name.startswith("test_") for p in test_patterns):
                continue

        file_data = idx.files[f]
        top_symbols = [
            s for s in file_data["symbols"]
            if s.get("parent") is None
        ]

        # Skip private symbols if requested
        if no_private:
            top_symbols = [s for s in top_symbols if not s["name"].startswith("_")]

        signatures = [s["signature"] for s in top_symbols]

        # Skip empty files
        if not signatures:
            continue

        entry = {"file": f, "symbols": signatures}
        result.append(entry)

    return result
