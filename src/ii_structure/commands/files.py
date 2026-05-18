import fnmatch
from ii_structure.index import Index


def execute(
    idx: Index,
    glob_pattern: str | None = None,
    path_prefix: str | None = None,
) -> list[str]:
    files = sorted(idx.files.keys())

    if path_prefix:
        files = [f for f in files if f.startswith(path_prefix)]

    if glob_pattern:
        files = [f for f in files if fnmatch.fnmatch(f, glob_pattern)]

    return files
