import hashlib
import pathlib

from ii_structure.index import Index
from ii_structure.backends import get_backend, get_language


def _file_content_hash(project_root: str, rel_path: str) -> str:
    """Compute SHA-256 hash of a file's content."""
    file_path = pathlib.Path(project_root) / rel_path
    content = file_path.read_text(encoding="utf-8", errors="replace")
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def execute(
    idx: Index,
    project_root: str,
    name: str,
    file_hint: str | None = None,
) -> dict | None:
    """Retrieve the full source code of a single symbol by name.

    Resolves the symbol via the index, then reads its complete definition
    from disk. Use file_hint to disambiguate when multiple symbols share
    the same name. Returns file path, line range, source text, and a
    content_hash for use with --expect-hash on write commands.
    """
    result = None

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
            result = backend.get_definition_source(
                project_root=project_root,
                name=name,
                index=idx,
                file_hint=file_hint,
            )

    if result is None:
        # Fallback to Python backend (preserves original behavior)
        from ii_structure.resolver import get_definition_source
        result = get_definition_source(
            project_root=project_root,
            name=name,
            index=idx,
            file_hint=file_hint,
        )

    # Attach content_hash so write commands can verify freshness
    if result is not None and "file" in result:
        result["content_hash"] = _file_content_hash(project_root, result["file"])

    return result
