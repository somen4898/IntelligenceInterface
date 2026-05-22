import hashlib
import pathlib

from ii_structure.index import Index


def execute(
    idx: Index,
    project_root: str,
    name: str,
    new_body: str,
    file_hint: str | None = None,
    expect_hash: str | None = None,
) -> dict:
    """Replace the full source of a symbol with new code.

    Resolves the symbol via the index, reads the file, splices out the old
    source at [line, end_line], splices in the new body with matched
    indentation, writes the file, and refreshes the index.
    """
    if not new_body.strip():
        raise ValueError("Empty replacement body")

    # 1. Resolve the symbol
    candidates = idx.search_symbols(name)
    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]

    if not candidates:
        raise ValueError(f"Symbol '{name}' not found in index")
    if len(candidates) > 1:
        files = sorted(set(c["file"] for c in candidates))
        raise ValueError(
            f"Multiple definitions found for '{name}'. "
            f"Use --file to disambiguate. Found in: {', '.join(files)}"
        )

    candidate = candidates[0]

    # 2. Read the file
    root = pathlib.Path(project_root)
    source_file = root / candidate["file"]
    if not source_file.exists():
        raise ValueError(f"File '{candidate['file']}' not found on disk")

    file_content = source_file.read_text(encoding="utf-8", errors="replace")

    # 2b. Verify content hash if provided
    if expect_hash is not None:
        actual_hash = f"sha256:{hashlib.sha256(file_content.encode()).hexdigest()[:16]}"
        if actual_hash != expect_hash:
            raise ValueError(
                f"File has changed since last read (hash mismatch). "
                f"Expected {expect_hash}, got {actual_hash}. "
                f"Re-read with 'body' to get the current content."
            )

    file_lines = file_content.splitlines()

    # 3. Detect indentation of the existing symbol
    start = candidate["line"] - 1  # 0-indexed inclusive
    end = candidate.get("end_line", candidate["line"])  # 0-indexed exclusive

    existing_first_line = file_lines[start]
    existing_indent = len(existing_first_line) - len(existing_first_line.lstrip())
    indent_str = existing_first_line[:existing_indent]

    # 4. Indent the new body to match
    new_body_lines = new_body.splitlines()
    if new_body_lines:
        # Detect base indent of the new body
        first_line = new_body_lines[0]
        new_base_indent = len(first_line) - len(first_line.lstrip())

        indented_lines = []
        for line in new_body_lines:
            if line.strip() == "":
                indented_lines.append("")
            else:
                # Remove old indent, apply new indent
                line_indent = len(line) - len(line.lstrip())
                relative_indent = line_indent - new_base_indent
                if relative_indent < 0:
                    relative_indent = 0
                indented_lines.append(indent_str + " " * relative_indent + line.lstrip())
    else:
        indented_lines = []

    # 5. Splice
    old_line_count = end - start
    new_lines = file_lines[:start] + indented_lines + file_lines[end:]

    # 6. Write the file
    source_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # 7. Refresh the index for this file
    # Re-parse the file with edge extraction
    from ii_structure.backends import get_backend
    content = source_file.read_text(encoding="utf-8", errors="replace")
    backend = get_backend(str(source_file))
    parse_result = backend.parse_file(str(source_file), content)

    # Compute file hash
    file_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    # Atomic update in graph — nodes + edges
    idx.graph.store_file_nodes_edges(
        candidate["file"], parse_result.symbols, parse_result.edges, file_hash
    )

    # Update aux data (imports, parse_error) if the index has file_aux
    if hasattr(idx, '_update_file_aux'):
        idx._update_file_aux(candidate["file"], parse_result, file_hash)

    # Resolve any new bare call targets
    idx.graph.resolve_bare_call_targets()
    idx.graph.commit()

    # Invalidate cache
    idx._invalidate_cache()

    # 8. Return structured result
    return {
        "file": candidate["file"],
        "symbol": name,
        "lines_removed": old_line_count,
        "lines_added": len(indented_lines),
        "new_range": [candidate["line"], candidate["line"] + len(indented_lines) - 1],
    }
