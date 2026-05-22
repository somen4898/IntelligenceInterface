import hashlib
import pathlib

from ii_structure.index import Index


def execute(
    idx: Index,
    project_root: str,
    anchor: str,
    position: str,  # "after" or "before"
    new_code: str,
    file_hint: str | None = None,
    expect_hash: str | None = None,
) -> dict:
    """Insert new code before or after an existing symbol.

    Resolves the anchor symbol, determines the insertion line,
    matches indentation to the anchor's level, inserts the code
    with a blank line separator, and refreshes the index.
    """
    if not new_code.strip():
        raise ValueError("Empty code body")

    # 1. Resolve the anchor symbol
    candidates = idx.search_symbols(anchor)
    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]

    if not candidates:
        raise ValueError(f"Symbol '{anchor}' not found in index")
    if len(candidates) > 1:
        files = sorted(set(c["file"] for c in candidates))
        raise ValueError(
            f"Multiple definitions found for '{anchor}'. "
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

    # 3. Determine insertion line (0-indexed)
    if position == "after":
        insert_at = candidate.get("end_line", candidate["line"])  # 0-indexed exclusive = after last line
    else:  # before
        insert_at = candidate["line"] - 1  # 0-indexed, before the first line

    # 4. Match indentation to anchor's level
    anchor_first_line = file_lines[candidate["line"] - 1]
    anchor_indent = len(anchor_first_line) - len(anchor_first_line.lstrip())
    indent_str = anchor_first_line[:anchor_indent]

    # Indent the new code
    code_lines = new_code.splitlines()
    if code_lines:
        first_line = code_lines[0]
        code_base_indent = len(first_line) - len(first_line.lstrip())

        indented_lines = []
        for line in code_lines:
            if line.strip() == "":
                indented_lines.append("")
            else:
                line_indent = len(line) - len(line.lstrip())
                relative_indent = line_indent - code_base_indent
                if relative_indent < 0:
                    relative_indent = 0
                indented_lines.append(indent_str + " " * relative_indent + line.lstrip())
    else:
        indented_lines = []

    # 5. Add blank line separator
    if position == "after":
        # Check if there's already a blank line after the anchor
        if insert_at < len(file_lines) and file_lines[insert_at].strip() != "":
            indented_lines = [""] + indented_lines
        elif insert_at >= len(file_lines):
            indented_lines = [""] + indented_lines
        # If there's already a blank line, just insert after it
        # (the blank line is already there)
        elif insert_at < len(file_lines) and file_lines[insert_at].strip() == "":
            # Blank line exists — insert after it
            insert_at += 1
    else:  # before
        # Check if there's already a blank line before the anchor
        if insert_at > 0 and file_lines[insert_at - 1].strip() != "":
            indented_lines = indented_lines + [""]
        elif insert_at > 0 and file_lines[insert_at - 1].strip() == "":
            # Blank line exists — insert before it
            pass
        else:
            indented_lines = indented_lines + [""]

    # 6. Splice and write
    # insert_at is 1-indexed for the return value
    insert_line_1indexed = insert_at + 1
    new_file_lines = file_lines[:insert_at] + indented_lines + file_lines[insert_at:]
    source_file.write_text("\n".join(new_file_lines) + "\n", encoding="utf-8")

    # 7. Refresh the index
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
        "anchor": anchor,
        "position": position,
        "lines_added": len(indented_lines),
        "inserted_range": [insert_line_1indexed, insert_line_1indexed + len(indented_lines) - 1],
    }
