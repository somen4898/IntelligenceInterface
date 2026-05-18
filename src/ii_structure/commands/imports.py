import pathlib
from ii_structure.index import Index


def execute(
    idx: Index,
    file: str,
    depth: int = 1,
    include_external: bool = False,
) -> dict:
    if file not in idx.files:
        raise FileNotFoundError(f"File '{file}' not found in index")

    project_files = set(idx.files.keys())

    # Forward: what does this file import?
    imports_out = _get_imports(idx, file, project_files, include_external, depth, set())

    # Reverse: what imports this file?
    imported_by = _get_importers(idx, file, project_files)

    # Mark hub nodes
    hub_threshold = 10
    hub_files = set()
    for f in project_files:
        count = sum(1 for other_f in project_files if other_f != f and _file_imports(idx, other_f, f, project_files))
        if count > hub_threshold:
            hub_files.add(f)

    result = {
        "file": file,
        "imports": imports_out,
        "imported_by": imported_by,
    }

    return result


def _get_imports(
    idx: Index,
    file: str,
    project_files: set[str],
    include_external: bool,
    depth: int,
    visited: set,
) -> list[dict]:
    if depth <= 0 or file in visited:
        return []
    visited.add(file)

    if file not in idx.files:
        return []

    results = []
    for imp in idx.files[file]["imports"]:
        module = imp["module"]
        resolved = _resolve_module(module, project_files)

        if resolved:
            entry = {"module": module, "file": resolved, "names": imp["names"]}
            results.append(entry)
            if depth > 1:
                sub = _get_imports(idx, resolved, project_files, include_external, depth - 1, visited)
                if sub:
                    entry["imports"] = sub
        elif include_external:
            results.append({"module": module, "file": None, "names": imp["names"], "external": True})

    return results


def _get_importers(idx: Index, file: str, project_files: set[str]) -> list[dict]:
    results = []
    target_module = _file_to_module(file)

    for other_file in sorted(project_files):
        if other_file == file:
            continue
        if other_file not in idx.files:
            continue
        for imp in idx.files[other_file]["imports"]:
            if _module_matches_file(imp["module"], file, project_files):
                results.append({
                    "file": other_file,
                    "module": imp["module"],
                    "names": imp["names"],
                })
                break
    return results


def _file_imports(idx: Index, source_file: str, target_file: str, project_files: set[str]) -> bool:
    if source_file not in idx.files:
        return False
    for imp in idx.files[source_file]["imports"]:
        if _module_matches_file(imp["module"], target_file, project_files):
            return True
    return False


def _resolve_module(module: str, project_files: set[str]) -> str | None:
    """Try to resolve a module name to a project file."""
    # Direct match: module "foo" -> "foo.py"
    candidates = [
        module.replace(".", "/") + ".py",
        module.replace(".", "/") + "/__init__.py",
    ]
    # Also try just the last component
    parts = module.split(".")
    candidates.append(parts[-1] + ".py")

    for candidate in candidates:
        if candidate in project_files:
            return candidate
    return None


def _module_matches_file(module: str, file: str, project_files: set[str]) -> bool:
    resolved = _resolve_module(module, project_files)
    return resolved == file


def _file_to_module(file: str) -> str:
    return file.replace("/", ".").replace(".py", "")
