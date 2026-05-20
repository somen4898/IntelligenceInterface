from ii_structure.index import Index
from ii_structure.backends import get_backend, get_language


def execute(
    idx: Index,
    project_root: str,
    name: str,
    file_hint: str | None = None,
) -> dict | None:
    """Retrieve the full source code of a single symbol by name.

    Resolves the symbol via the index, then reads its complete definition
    from disk. Use file_hint to disambiguate when multiple symbols share
    the same name. Returns file path, line range, and source text.
    """
    # Find the symbol first to know which file/language
    candidates = idx.search_symbols(name)
    if candidates:
        # If file_hint provided, filter first
        if file_hint:
            filtered = [c for c in candidates if c["file"] == file_hint]
            if filtered:
                candidates = filtered

        file_path = candidates[0]["file"]
        lang = get_language(file_path)
        if lang:
            backend = get_backend(file_path)
            return backend.get_definition_source(
                project_root=project_root,
                name=name,
                index=idx,
                file_hint=file_hint,
            )

    # Fallback to Python backend (preserves original behavior)
    from ii_structure.resolver import get_definition_source
    return get_definition_source(
        project_root=project_root,
        name=name,
        index=idx,
        file_hint=file_hint,
    )
