import textwrap
from ii_structure.parser import parse_file


def test_extracts_function_call():
    source = textwrap.dedent("""\
        def caller():
            helper()
        def helper():
            return 42
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert len(call_edges) >= 1
    targets = {e.target for e in call_edges}
    assert "helper" in targets


def test_extracts_method_call():
    source = textwrap.dedent("""\
        class User:
            def save(self):
                pass
            def process(self):
                self.save()
    """)
    result = parse_file("models.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "save" in targets


def test_extracts_imported_call():
    source = textwrap.dedent("""\
        from utils import validate
        def process(data):
            validate(data)
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "validate" in targets


def test_extracts_import_edges():
    source = textwrap.dedent("""\
        from models import User
        import os
    """)
    result = parse_file("app.py", source)
    import_edges = [e for e in result.edges if e.kind == "IMPORTS"]
    assert len(import_edges) >= 1


def test_extracts_tested_by_edges():
    source = textwrap.dedent("""\
        def test_save():
            user = User()
            user.save()
    """)
    result = parse_file("test_models.py", source)
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(tested_edges) >= 1


def test_no_call_edges_from_class_definition():
    source = textwrap.dedent("""\
        class User:
            pass
    """)
    result = parse_file("models.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert len(call_edges) == 0


def test_nested_call_extraction():
    source = textwrap.dedent("""\
        def process():
            result = transform(validate(data))
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "transform" in targets
    assert "validate" in targets


def test_edge_has_line_number():
    source = textwrap.dedent("""\
        def caller():
            helper()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert all(e.line > 0 for e in call_edges)


def test_edge_has_source_qualified():
    source = textwrap.dedent("""\
        def caller():
            helper()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    assert any("caller" in e.source for e in call_edges)


def test_method_call_has_class_in_source():
    source = textwrap.dedent("""\
        class MyClass:
            def method(self):
                self.helper()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    sources = {e.source for e in call_edges}
    assert any("MyClass.method" in s for s in sources)


def test_existing_parse_still_works():
    """ParseResult still has symbols and imports."""
    source = textwrap.dedent("""\
        from os import path
        class Foo:
            def bar(self):
                pass
    """)
    result = parse_file("test.py", source)
    assert len(result.symbols) >= 1
    assert len(result.imports) >= 1
    assert result.edges is not None
    assert result.error is None
