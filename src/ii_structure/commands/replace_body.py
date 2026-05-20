import pathlib

from ii_structure.index import Index, _parse_and_build_entry


def execute(
    idx: Index,
    project_root: str,
    name: str,
    new_body: str,
    file_hint: str | None = None,
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
    idx.files[candidate["file"]] = _parse_and_build_entry(source_file)
    state_dir = root / ".ii-structure"
    if state_dir.exists():
        idx.save(state_dir)

    # 8. Return structured result
    return {
        "file": candidate["file"],
        "symbol": name,
        "lines_removed": old_line_count,
        "lines_added": len(indented_lines),
        "new_range": [candidate["line"], candidate["line"] + len(indented_lines) - 1],
    }
