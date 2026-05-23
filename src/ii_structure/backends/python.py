from ii_structure.parser import parse_file as _parse_file, ParseResult
from ii_structure.resolver import (
    get_definition_source as _get_definition_source,
)


class PythonBackend:
    def parse_file(self, file_path: str, source: str) -> ParseResult:
        return _parse_file(file_path, source)

    def get_definition_source(self, project_root, name, index, file_hint=None):
        return _get_definition_source(project_root, name, index, file_hint)
