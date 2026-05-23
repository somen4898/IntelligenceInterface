from ii_structure.index import Index
from collections import defaultdict


def execute(idx: Index, project_root: str) -> dict:
    """Graph-powered project overview — structure, key files, entry points."""
    all_files = sorted(idx.graph.get_all_files())
    stats = idx.graph.get_stats()

    # 1. Directory structure with counts
    dir_tree = defaultdict(lambda: {"files": 0, "classes": 0, "functions": 0})
    for f in all_files:
        parts = f.rsplit("/", 1)
        dir_name = parts[0] + "/" if len(parts) > 1 else "./"
        dir_tree[dir_name]["files"] += 1
        for node in idx.graph.get_nodes_by_file(f):
            if node["kind"] == "class":
                dir_tree[dir_name]["classes"] += 1
            elif node["kind"] in ("function", "method"):
                dir_tree[dir_name]["functions"] += 1

    structure = []
    for dir_path in sorted(dir_tree.keys()):
        info = dir_tree[dir_path]
        # Skip test directories in the structure summary
        if any(t in dir_path for t in ("test/", "tests/", "test_", "fixture")):
            continue
        structure.append({
            "directory": dir_path,
            "files": info["files"],
            "classes": info["classes"],
            "functions": info["functions"],
        })

    # 2. Most important files — ranked by incoming edges (most depended on)
    file_importance = defaultdict(int)
    for f in all_files:
        for node in idx.graph.get_nodes_by_file(f):
            qn = node["qualified_name"]
            incoming = idx.graph.get_edges_by_target(qn)
            file_importance[f] += len(incoming)

    # Also count files that import this file
    for f in all_files:
        incoming_imports = [e for e in idx.graph.get_edges_by_target(f) if e["kind"] == "IMPORTS"]
        file_importance[f] += len(incoming_imports) * 2  # imports weighted more

    top_files = sorted(file_importance.items(), key=lambda x: -x[1])[:10]
    key_files = []
    for f, score in top_files:
        if score == 0:
            continue
        nodes = idx.graph.get_nodes_by_file(f)
        classes = [n["name"] for n in nodes if n["kind"] == "class"]
        functions = [n["name"] for n in nodes if n["kind"] == "function" and not n["name"].startswith("_")]
        key_files.append({
            "file": f,
            "importance": score,
            "classes": classes[:5],
            "functions": functions[:5],
        })

    # 3. Entry points — files with main, __main__, app, or CLI commands
    entry_points = []
    entry_names = {"main", "__main__", "create_app", "app", "cli", "run", "start"}
    for f in all_files:
        for node in idx.graph.get_nodes_by_file(f):
            if node["name"] in entry_names or node["name"].startswith("@"):
                entry_points.append({"file": f, "symbol": node["name"]})
                break

    # 4. Languages detected
    languages = set()
    for f in all_files:
        if f.endswith(".py"):
            languages.add("python")
        elif f.endswith(".go"):
            languages.add("go")
        elif f.endswith((".ts", ".tsx")):
            languages.add("typescript")

    # 5. Test stats
    test_files = [f for f in all_files if any(
        t in f for t in ("test_", "_test.", ".test.", ".spec.", "conftest", "tests/", "test/")
    )]

    return {
        "total_files": len(all_files),
        "total_symbols": stats["total_nodes"],
        "total_edges": stats["total_edges"],
        "languages": sorted(languages),
        "structure": structure,
        "key_files": key_files[:7],
        "entry_points": entry_points[:5],
        "test_files": len(test_files),
        "source_files": len(all_files) - len(test_files),
    }
