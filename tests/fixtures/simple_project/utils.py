"""Utility functions."""

import json
from typing import Any


def load_config(path: str) -> dict[str, Any]:
    """Load a JSON config file."""
    with open(path) as f:
        return json.load(f)


class Singleton:
    """A singleton base class."""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class ConfigManager(Singleton):
    """Manages application configuration."""

    def __init__(self):
        self.data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        """Get a config value."""
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set a config value."""
        self.data[key] = value
