from ii_structure.index import Index
from ii_structure.resolver import find_usages


def execute(
    idx: Index,
    project_root: str,
    name: str,
    path_scope: str | None = None,
    kind_filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return find_usages(
        project_root=project_root,
        name=name,
        index=idx,
        path_scope=path_scope,
        kind_filter=kind_filter,
        limit=limit,
    )
