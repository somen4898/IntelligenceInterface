from __future__ import annotations
from typing import Protocol
from ii_structure.parser import ParseResult


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

    def get_definition_source(
        self,
        project_root: str,
        name: str,
        index,
        file_hint: str | None = None,
    ) -> dict | None:
        """Get the full source body of a symbol."""
        ...
