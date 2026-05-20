from ii_structure.parser import parse_file as _parse_file, ParseResult
from ii_structure.resolver import (
    find_usages as _find_usages,
    get_definition_source as _get_definition_source,
)


class PythonBackend:
    def parse_file(self, file_path: str, source: str) -> ParseResult:
        return _parse_file(file_path, source)

    def find_usages(self, project_root, name, index, path_scope=None, kind_filter=None, limit=50, include_tests=True):
        return _find_usages(project_root, name, index, path_scope, kind_filter, limit, include_tests)

    def get_definition_source(self, project_root, name, index, file_hint=None):
        return _get_definition_source(project_root, name, index, file_hint)
