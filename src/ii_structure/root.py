import pathlib

MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", ".git")


def find_project_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    while True:
        for marker in MARKERS:
            candidate = current / marker
            if candidate.exists():
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"No project root found from {start}. "
        "Looked for: pyproject.toml, setup.py, setup.cfg, .git. "
        "Use --project to specify the root."
    )
