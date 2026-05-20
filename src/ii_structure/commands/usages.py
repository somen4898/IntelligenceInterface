from ii_structure.index import Index
from ii_structure.backends import get_backend, get_language


def execute(
    idx: Index,
    project_root: str,
    name: str,
    path_scope: str | None = None,
    kind_filter: str | None = None,
    limit: int = 50,
    include_tests: bool = True,
) -> list[dict]:
    """Find all references to a symbol, resolved by type analysis.

    Uses language-specific backends (Jedi for Python, tsserver for TypeScript,
    gopls for Go) to find accurate call sites and references. Filter results
    by path_scope, kind_filter, or exclude test files with include_tests=False.
    """
    # Find the symbol first to know which file/language
    candidates = idx.search_symbols(name)
    if candidates:
        file_path = candidates[0]["file"]
        lang = get_language(file_path)
        if lang:
            backend = get_backend(file_path)
            return backend.find_usages(
                project_root=project_root,
                name=name,
                index=idx,
                path_scope=path_scope,
                kind_filter=kind_filter,
                limit=limit,
                include_tests=include_tests,
            )

    # Fallback to Python backend (preserves original behavior)
    from ii_structure.resolver import find_usages
    return find_usages(
        project_root=project_root,
        name=name,
        index=idx,
        path_scope=path_scope,
        kind_filter=kind_filter,
        limit=limit,
        include_tests=include_tests,
    )
