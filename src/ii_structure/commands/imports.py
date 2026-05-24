from ii_structure.index import Index


def execute(
    idx: Index,
    file: str,
    depth: int = 1,
    include_external: bool = False,
) -> dict:
    """Build forward and reverse dependency graph from pre-computed edges."""
    # Check file exists in index
    if file not in idx.files:
        raise FileNotFoundError(f"File '{file}' not found in index")

    # Forward imports: what does this file import?
    # Use the aux-stored imports data (same as before) for rich info
    file_data = idx.files[file]
    project_files = set(idx.files.keys())

    imports = []
    for imp in file_data["imports"]:
        module = imp["module"]
        resolved = _resolve_module(module, project_files)

        is_project = resolved is not None

        if not include_external and not is_project:
            continue

        entry = {
            "module": module,
            "file": resolved,
            "names": imp.get("names", []),
        }
        if not is_project:
            entry["external"] = True

        imports.append(entry)

    # Reverse imports: who imports from this file?
    imported_by = []
    for other_file in sorted(project_files):
        if other_file == file:
            continue
        other_data = idx.files.get(other_file)
        if other_data is None:
            continue
        for imp in other_data["imports"]:
            if _module_matches_file(imp["module"], file, project_files):
                imported_by.append({
                    "file": other_file,
                    "module": imp["module"],
                    "names": imp.get("names", []),
                })
                break

    return {
        "file": file,
        "imports": imports,
        "imported_by": imported_by,
    }


def _resolve_module(module: str, project_files: set[str]) -> str | None:
    """Try to resolve a module name to a project file."""
    candidates = [
        module.replace(".", "/") + ".py",
        module.replace(".", "/") + "/__init__.py",
    ]
    parts = module.split(".")
    candidates.append(parts[-1] + ".py")

    for candidate in candidates:
        # Direct match
        if candidate in project_files:
            return candidate
        # Match with source prefix (e.g. "src/ii_structure/graph.py")
        for f in project_files:
            if f.endswith("/" + candidate):
                return f
    return None


def _module_matches_file(module: str, file: str, project_files: set[str]) -> bool:
    resolved = _resolve_module(module, project_files)
    return resolved == file
