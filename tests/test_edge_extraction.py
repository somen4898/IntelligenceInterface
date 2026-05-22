import textwrap
from ii_structure.parser import parse_file
from ii_structure.backends.golang import GoBackend
from ii_structure.backends.typescript import TypeScriptBackend


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


# ── Go backend edge extraction tests ──


def test_go_extracts_function_call():
    source = """\
package main

func caller() {
    helper()
}

func helper() int {
    return 42
}
"""
    backend = GoBackend()
    result = backend.parse_file("main.go", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "helper" in targets


def test_go_extracts_method_call():
    source = """\
package main

type Server struct{}

func (s *Server) Start() {
    s.Init()
}

func (s *Server) Init() {}
"""
    backend = GoBackend()
    result = backend.parse_file("server.go", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "Init" in targets


def test_go_extracts_import_edges():
    source = """\
package main

import "fmt"

func main() {
    fmt.Println("hello")
}
"""
    backend = GoBackend()
    result = backend.parse_file("main.go", source)
    import_edges = [e for e in result.edges if e.kind == "IMPORTS"]
    assert len(import_edges) >= 1


# ── TypeScript backend edge extraction tests ──


def test_ts_extracts_function_call():
    source = """\
function caller(): void {
    helper();
}

function helper(): number {
    return 42;
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "helper" in targets


def test_ts_extracts_new_expression():
    source = """\
class User {}

function createUser(): User {
    return new User();
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "User" in targets


def test_ts_extracts_method_call():
    source = """\
class Service {
    save(): void {
        this.validate();
    }
    validate(): boolean {
        return true;
    }
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("service.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "validate" in targets


def test_ts_extracts_import_edges():
    source = """\
import { User } from './models';

function getUser(): User {
    return new User();
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    import_edges = [e for e in result.edges if e.kind == "IMPORTS"]
    assert len(import_edges) >= 1


# ── Go TESTED_BY edge extraction tests ──


def test_go_test_file_generates_tested_by():
    source = """\
package main

import "testing"

func TestCreateUser(t *testing.T) {
    CreateUser("test")
}
"""
    backend = GoBackend()
    result = backend.parse_file("user_test.go", source)
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(tested_edges) >= 1
    targets = {e.target for e in tested_edges}
    assert "CreateUser" in targets


def test_go_non_test_file_generates_calls():
    source = """\
package main

func caller() { helper() }
func helper() {}
"""
    backend = GoBackend()
    result = backend.parse_file("main.go", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(call_edges) >= 1
    assert len(tested_edges) == 0


# ── TypeScript TESTED_BY edge extraction tests ──


def test_ts_test_file_generates_tested_by():
    source = """\
function testHelper(): number { return 42; }

function testCreateUser(): void {
    createUser("test");
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("user.test.ts", source)
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(tested_edges) >= 1


def test_ts_spec_file_generates_tested_by():
    source = """\
function testSave(): void {
    save();
}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("user.spec.ts", source)
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(tested_edges) >= 1


def test_ts_non_test_file_generates_calls():
    source = """\
function caller(): void { helper(); }
function helper(): void {}
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    tested_edges = [e for e in result.edges if e.kind == "TESTED_BY"]
    assert len(call_edges) >= 1
    assert len(tested_edges) == 0


# ── Same-file call target qualification tests ──


def test_python_same_file_call_qualified():
    """Call to a function defined in the same file should be fully qualified."""
    source = textwrap.dedent("""\
        def helper():
            return 42

        def caller():
            helper()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "app.py::helper" in targets


def test_python_method_call_same_class_qualified():
    """self.save() in same class should resolve to qualified name."""
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
    assert "models.py::User.save" in targets


def test_python_cross_file_call_stays_bare():
    """Call to a function NOT defined in this file stays bare."""
    source = textwrap.dedent("""\
        from utils import validate
        def process():
            validate()
    """)
    result = parse_file("app.py", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "validate" in targets
    assert "app.py::validate" not in targets


def test_go_same_file_call_qualified():
    source = """\
package main

func helper() int { return 42 }

func caller() { helper() }
"""
    backend = GoBackend()
    result = backend.parse_file("main.go", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "main.go::helper" in targets


def test_ts_same_file_call_qualified():
    source = """\
function helper(): number { return 42; }

function caller(): void { helper(); }
"""
    backend = TypeScriptBackend()
    result = backend.parse_file("app.ts", source)
    call_edges = [e for e in result.edges if e.kind == "CALLS"]
    targets = {e.target for e in call_edges}
    assert "app.ts::helper" in targets
