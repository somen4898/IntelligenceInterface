import hashlib
import json
import pathlib
from dataclasses import asdict

import pathspec

from ii_structure.backends import get_backend, get_language, supported_extensions

INDEX_VERSION = 1
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules", ".ii-structure", ".pytest_cache"}


class Index:
    def __init__(
        self,
        project_root: str,
        files: dict,
        version: int = INDEX_VERSION,
    ):
        self.project_root = project_root
        self.files = files
        self.version = version

    @classmethod
    def build(cls, root: pathlib.Path) -> "Index":
        root = root.resolve()
        gitignore_spec = _load_gitignore(root)
        files = {}
        for source_file in _walk_source_files(root, gitignore_spec):
            rel = str(source_file.relative_to(root))
            entry = _parse_and_build_entry(source_file)
            files[rel] = entry
        return cls(project_root=str(root), files=files)

    def save(self, state_dir: pathlib.Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.version,
            "project_root": self.project_root,
            "files": self.files,
        }
        index_path = state_dir / "index.json"
        index_path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, state_dir: pathlib.Path) -> "Index":
        index_path = state_dir / "index.json"
        data = json.loads(index_path.read_text())
        return cls(
            project_root=data["project_root"],
            files=data["files"],
            version=data.get("version", INDEX_VERSION),
        )

    def refresh(self, root: pathlib.Path) -> None:
        root = root.resolve()
        gitignore_spec = _load_gitignore(root)
        current_files = set()

        for source_file in _walk_source_files(root, gitignore_spec):
            rel = str(source_file.relative_to(root))
            current_files.add(rel)
            if rel in self.files:
                stored_mtime = self.files[rel].get("mtime", 0)
                actual_mtime = source_file.stat().st_mtime
                if actual_mtime != stored_mtime:
                    content = source_file.read_text(encoding="utf-8", errors="replace")
                    actual_hash = _content_hash(content)
                    if actual_hash != self.files[rel].get("content_hash"):
                        self.files[rel] = _parse_and_build_entry(source_file)
                    else:
                        self.files[rel]["mtime"] = actual_mtime
            else:
                self.files[rel] = _parse_and_build_entry(source_file)

        stale_keys = set(self.files.keys()) - current_files
        for key in stale_keys:
            del self.files[key]

    def get_symbols(self, rel_path: str) -> list[dict]:
        if rel_path in self.files:
            return self.files[rel_path]["symbols"]
        return []

    def search_symbols(self, name_path: str) -> list[dict]:
        results = []
        parts = name_path.strip("/").split("/")

        for rel_path, file_data in self.files.items():
            for symbol in file_data["symbols"]:
                if len(parts) == 1:
                    if symbol["name"] == parts[0]:
                        results.append({**symbol, "file": rel_path})
                elif len(parts) == 2:
                    if symbol["name"] == parts[-1] and symbol.get("parent") == parts[0]:
                        results.append({**symbol, "file": rel_path})
                else:
                    full_path = symbol["name"]
                    if symbol.get("parent"):
                        full_path = f"{symbol['parent']}/{symbol['name']}"
                    if full_path == name_path.strip("/"):
                        results.append({**symbol, "file": rel_path})

        return results

    def all_symbols(self) -> list[dict]:
        results = []
        for rel_path, file_data in self.files.items():
            for symbol in file_data["symbols"]:
                results.append({**symbol, "file": rel_path})
        return results


def load_or_build_index(root: pathlib.Path) -> Index:
    state_dir = root / ".ii-structure"
    index_path = state_dir / "index.json"

    if index_path.exists():
        try:
            idx = Index.load(state_dir)
            idx.refresh(root)
            idx.save(state_dir)
            return idx
        except (json.JSONDecodeError, KeyError):
            pass

    idx = Index.build(root)
    idx.save(state_dir)
    return idx


def _parse_and_build_entry(source_file: pathlib.Path) -> dict:
    content = source_file.read_text(encoding="utf-8", errors="replace")
    backend = get_backend(str(source_file))
    result = backend.parse_file(str(source_file), content)
    return {
        "mtime": source_file.stat().st_mtime,
        "content_hash": _content_hash(content),
        "symbols": [asdict(s) for s in result.symbols],
        "imports": [asdict(i) for i in result.imports],
        "parse_error": result.error,
    }


def _content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _load_gitignore(root: pathlib.Path) -> pathspec.PathSpec | None:
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        patterns = gitignore_path.read_text().splitlines()
        return pathspec.PathSpec.from_lines("gitignore", patterns)
    return None


def _walk_source_files(
    root: pathlib.Path,
    gitignore_spec: pathspec.PathSpec | None,
) -> list[pathlib.Path]:
    files = []
    extensions = supported_extensions()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if gitignore_spec and gitignore_spec.match_file(str(rel)):
            continue
        files.append(path)
    return files
