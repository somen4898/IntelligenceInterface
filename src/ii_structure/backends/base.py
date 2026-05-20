from __future__ import annotations
from typing import Protocol
from ii_structure.parser import SymbolInfo, ImportInfo, ParseResult


LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
}


class LanguageBackend(Protocol):
    """Interface that every language backend must implement."""

    def parse_file(self, file_path: str, source: str) -> ParseResult:
        """Parse source and extract symbols + imports."""
        ...

    def find_usages(
        self,
        project_root: str,
        name: str,
        index,  # Index type — avoid circular import
        path_scope: str | None = None,
        kind_filter: str | None = None,
        limit: int = 50,
        include_tests: bool = True,
    ) -> list[dict]:
        """Find all references to a symbol."""
        ...

    def get_definition_source(
        self,
        project_root: str,
        name: str,
        index,
        file_hint: str | None = None,
    ) -> dict | None:
        """Get the full source body of a symbol."""
        ...
