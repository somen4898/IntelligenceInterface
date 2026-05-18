from ii_structure.index import Index
from ii_structure.resolver import get_definition_source


def execute(
    idx: Index,
    project_root: str,
    name: str,
    file_hint: str | None = None,
) -> dict | None:
    return get_definition_source(
        project_root=project_root,
        name=name,
        index=idx,
        file_hint=file_hint,
    )
