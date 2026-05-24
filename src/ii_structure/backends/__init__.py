from __future__ import annotations
import logging
import pathlib
from ii_structure.backends.base import LanguageBackend, LANGUAGE_EXTENSIONS

logger = logging.getLogger(__name__)


_backends: dict[str, LanguageBackend] = {}


def get_backend(file_path: str) -> LanguageBackend:
    """Get the appropriate backend for a file based on its extension."""
    ext = pathlib.Path(file_path).suffix
    lang = LANGUAGE_EXTENSIONS.get(ext)

    if lang is None:
        raise ValueError(f"Unsupported file type: {ext}")

    if lang not in _backends:
        if lang == "python":
            from ii_structure.backends.python import PythonBackend
            _backends[lang] = PythonBackend()
            logger.debug("Loaded %s backend", lang)
        elif lang == "go":
            from ii_structure.backends.golang import GoBackend
            _backends[lang] = GoBackend()
            logger.debug("Loaded %s backend", lang)
        elif lang == "typescript":
            from ii_structure.backends.typescript import TypeScriptBackend
            _backends[lang] = TypeScriptBackend()
            logger.debug("Loaded %s backend", lang)
        else:
            raise ValueError(f"No backend registered for language: {lang}")

    return _backends[lang]


def get_language(file_path: str) -> str | None:
    """Return the language name for a file, or None if unsupported."""
    ext = pathlib.Path(file_path).suffix
    return LANGUAGE_EXTENSIONS.get(ext)


def supported_extensions() -> set[str]:
    """Return all supported file extensions."""
    return set(LANGUAGE_EXTENSIONS.keys())
