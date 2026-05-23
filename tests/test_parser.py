from ii_structure.parser import parse_file


SIMPLE_CLASS = '''\
"""Module docstring."""

from dataclasses import dataclass


@dataclass
class User:
    """A user in the system."""
    name: str
    email: str

    def save(self) -> None:
        """Persist the user."""
        pass

    def delete(self) -> None:
        """Remove the user."""
        pass


MAX_USERS = 100
'''

SIMPLE_FUNCTION = '''\
import os
from typing import Any


def load_config(path: str) -> dict[str, Any]:
    """Load a JSON config file."""
    with open(path) as f:
        return {}
'''

ASYNC_FUNCTION = '''\
async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    pass
'''

NESTED_CLASSES = '''\
class Outer:
    """Outer class."""

    class Inner:
        """Inner class."""

        def inner_method(self):
            pass

    def outer_method(self):
        pass
'''

SYNTAX_ERROR = '''\
def broken(
    this is not valid python
'''

EMPTY_FILE = ''


# --- Symbol extraction tests ---

def test_extracts_class():
    result = parse_file("test.py", SIMPLE_CLASS)
    assert result.error is None
    classes = [s for s in result.symbols if s.kind == "class"]
    assert len(classes) == 1
    assert classes[0].name == "User"
    assert classes[0].docstring == "A user in the system."
    assert "dataclass" in classes[0].signature


def test_extracts_methods():
    result = parse_file("test.py", SIMPLE_CLASS)
    methods = [s for s in result.symbols if s.kind == "method"]
    assert len(methods) == 2
    names = {m.name for m in methods}
    assert names == {"save", "delete"}
    assert all(m.parent == "User" for m in methods)


def test_extracts_function():
    result = parse_file("test.py", SIMPLE_FUNCTION)
    functions = [s for s in result.symbols if s.kind == "function"]
    assert len(functions) == 1
    assert functions[0].name == "load_config"
    assert "path: str" in functions[0].signature
    assert "dict[str, Any]" in functions[0].signature
    assert functions[0].docstring == "Load a JSON config file."


def test_extracts_async_function():
    result = parse_file("test.py", ASYNC_FUNCTION)
    functions = [s for s in result.symbols if s.kind == "function"]
    assert len(functions) == 1
    assert functions[0].name == "fetch_data"
    assert "async" in functions[0].signature


def test_extracts_variable():
    result = parse_file("test.py", SIMPLE_CLASS)
    variables = [s for s in result.symbols if s.kind == "variable"]
    assert len(variables) == 1
    assert variables[0].name == "MAX_USERS"


def test_extracts_nested_classes():
    result = parse_file("test.py", NESTED_CLASSES)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert len(classes) == 2
    inner = [c for c in classes if c.name == "Inner"][0]
    assert inner.parent == "Outer"
    methods = [s for s in result.symbols if s.kind == "method"]
    inner_methods = [m for m in methods if m.parent == "Outer/Inner"]
    assert len(inner_methods) == 1
    assert inner_methods[0].name == "inner_method"


def test_extracts_children():
    result = parse_file("test.py", SIMPLE_CLASS)
    user = [s for s in result.symbols if s.name == "User"][0]
    assert "save" in user.children
    assert "delete" in user.children


# --- Import extraction tests ---

def test_extracts_import():
    result = parse_file("test.py", SIMPLE_FUNCTION)
    imports = result.imports
    assert len(imports) == 2
    os_import = [i for i in imports if i.module == "os"][0]
    assert os_import.names == []
    assert os_import.is_relative is False


def test_extracts_from_import():
    result = parse_file("test.py", SIMPLE_FUNCTION)
    typing_import = [i for i in result.imports if i.module == "typing"][0]
    assert "Any" in typing_import.names


def test_extracts_relative_import():
    source = "from . import utils\nfrom ..models import User\n"
    result = parse_file("test.py", source)
    rel = [i for i in result.imports if i.is_relative]
    assert len(rel) == 2


# --- Error handling tests ---

def test_syntax_error_captured():
    result = parse_file("test.py", SYNTAX_ERROR)
    assert result.error is not None
    assert result.symbols == []
    assert result.imports == []


def test_empty_file():
    result = parse_file("test.py", EMPTY_FILE)
    assert result.error is None
    assert result.symbols == []
    assert result.imports == []


# --- Signature tests ---

def test_class_signature_includes_bases():
    source = "class Dog(Animal, Serializable):\n    pass\n"
    result = parse_file("test.py", source)
    cls = result.symbols[0]
    assert "Animal" in cls.signature
    assert "Serializable" in cls.signature


def test_method_signature_includes_decorator():
    source = '''\
class Foo:
    @staticmethod
    def bar(x: int) -> int:
        return x
'''
    result = parse_file("test.py", source)
    method = [s for s in result.symbols if s.name == "bar"][0]
    assert "staticmethod" in method.decorators
