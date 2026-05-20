"""Edge case tests for replace-body and insert-symbol write commands.

Covers: indentation (nested, mixed, zero, deep), boundary conditions,
multiline strings, decorators, empty classes, single-line functions,
trailing whitespace, unicode, and file-level edge cases.
"""
import textwrap

import pytest

from ii_structure.index import Index


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def nested_class_project(tmp_path):
    """Project with deeply nested classes and methods."""
    src = tmp_path / "nested.py"
    src.write_text(textwrap.dedent('''\
        class Outer:
            class Inner:
                class DeepNested:
                    def deep_method(self):
                        return "deep"

                def inner_method(self):
                    return "inner"

            def outer_method(self):
                return "outer"

        def top_level():
            return "top"
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def decorated_project(tmp_path):
    """Project with decorated functions and methods."""
    src = tmp_path / "decorated.py"
    src.write_text(textwrap.dedent('''\
        import functools

        def my_decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper

        class Service:
            @staticmethod
            def static_method():
                return True

            @classmethod
            def class_method(cls):
                return cls()

            @my_decorator
            def decorated_method(self):
                return "decorated"

            def plain_method(self):
                return "plain"
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def multiline_string_project(tmp_path):
    """Project with multiline strings in method bodies."""
    src = tmp_path / "strings.py"
    src.write_text(textwrap.dedent('''\
        class Formatter:
            def template(self):
                return """
                Hello {name},
                Welcome to {place}.
                """

            def sql_query(self):
                query = """
                    SELECT *
                    FROM users
                    WHERE active = 1
                """
                return query
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def single_line_project(tmp_path):
    """Project with single-line functions and empty classes."""
    src = tmp_path / "minimal.py"
    src.write_text(textwrap.dedent('''\
        class Empty:
            pass

        class WithDocOnly:
            """Just a docstring."""

        def one_liner(): return 42

        def two_liner():
            return 99

        class Container:
            def method_a(self): return "a"

            def method_b(self): return "b"
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def whitespace_project(tmp_path):
    """Project with trailing whitespace and blank lines in methods."""
    src = tmp_path / "spaces.py"
    # Intentionally has trailing whitespace and odd blank lines
    src.write_text(
        "class Messy:\n"
        "    def method_a(self):\n"
        "        x = 1  \n"         # trailing whitespace
        "        \n"                 # blank line with spaces
        "        return x\n"
        "\n"
        "    def method_b(self):\n"
        "        return 2\n"
    )
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def unicode_project(tmp_path):
    """Project with unicode in symbol bodies."""
    src = tmp_path / "unicode.py"
    src.write_text(textwrap.dedent('''\
        class Greeter:
            def greet(self, name: str) -> str:
                return f"こんにちは {name}! 🎉"

            def farewell(self, name: str) -> str:
                return f"さようなら {name}"
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


@pytest.fixture
def indented_input_project(tmp_path):
    """Standard project for testing various input indentation levels."""
    src = tmp_path / "standard.py"
    src.write_text(textwrap.dedent('''\
        class Calculator:
            def add(self, a, b):
                return a + b

            def subtract(self, a, b):
                return a - b

            def multiply(self, a, b):
                return a * b
    '''))
    idx = Index.build(tmp_path)
    return tmp_path, idx


# ============================================================
# REPLACE-BODY: Indentation Tests
# ============================================================

class TestReplaceBodyIndentation:

    def test_replace_deeply_nested_method(self, nested_class_project):
        """Replace a method 3 levels deep — indentation must be 12 spaces."""
        tmp_path, idx = nested_class_project
        from ii_structure.commands.replace_body import execute

        new_body = "def deep_method(self):\n    return 'updated deep'"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="DeepNested/deep_method",
            new_body=new_body,
        )

        content = (tmp_path / "nested.py").read_text()
        lines = content.splitlines()
        deep_line = [line for line in lines if "def deep_method" in line][0]
        body_line = [line for line in lines if "updated deep" in line][0]

        # Outer(4) + Inner(8) + DeepNested(12) = 12 spaces for method
        assert deep_line.startswith("            def deep_method")
        # Method body = 16 spaces
        assert body_line.startswith("                return")

    def test_replace_top_level_keeps_zero_indent(self, nested_class_project):
        """Replacing top-level function should have zero indentation."""
        tmp_path, idx = nested_class_project
        from ii_structure.commands.replace_body import execute

        new_body = "def top_level():\n    return 'updated top'"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="top_level",
            new_body=new_body,
        )

        content = (tmp_path / "nested.py").read_text()
        lines = content.splitlines()
        top_line = [line for line in lines if "def top_level" in line][0]
        assert top_line == "def top_level():"
        body_line = [line for line in lines if "updated top" in line][0]
        assert body_line == "    return 'updated top'"

    def test_replace_with_already_indented_input(self, indented_input_project):
        """New body already has 4-space indent — should normalize to method level."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        # Input already indented at 4 spaces (same as target)
        new_body = "    def add(self, a, b):\n        result = a + b\n        return result"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body=new_body,
        )

        content = (tmp_path / "standard.py").read_text()
        lines = content.splitlines()
        add_line = [line for line in lines if "def add" in line][0]
        assert add_line == "    def add(self, a, b):"
        result_line = [line for line in lines if "result = a + b" in line][0]
        assert result_line == "        result = a + b"

    def test_replace_with_over_indented_input(self, indented_input_project):
        """New body indented at 8 spaces — should normalize to 4."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        # Input over-indented at 8 spaces
        new_body = "        def add(self, a, b):\n            return a + b + 1"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body=new_body,
        )

        content = (tmp_path / "standard.py").read_text()
        lines = content.splitlines()
        add_line = [line for line in lines if "def add" in line][0]
        assert add_line == "    def add(self, a, b):"
        body_line = [line for line in lines if "a + b + 1" in line][0]
        assert body_line == "        return a + b + 1"

    def test_replace_preserves_blank_lines_in_body(self, indented_input_project):
        """Blank lines within the new body should be preserved as empty lines."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        new_body = "def add(self, a, b):\n    # validate\n\n    return a + b"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body=new_body,
        )

        content = (tmp_path / "standard.py").read_text()
        lines = content.splitlines()
        # Find the blank line between validate comment and return
        validate_idx = next(i for i, line in enumerate(lines) if "# validate" in line)
        assert lines[validate_idx + 1] == ""  # blank line preserved
        assert "return a + b" in lines[validate_idx + 2]


# ============================================================
# REPLACE-BODY: Boundary and Special Cases
# ============================================================

class TestReplaceBodyBoundary:

    def test_replace_decorated_method(self, decorated_project):
        """Replacing a decorated method should replace including the decorator."""
        tmp_path, idx = decorated_project
        from ii_structure.commands.replace_body import execute

        new_body = "@my_decorator\ndef decorated_method(self):\n    return 'new decorated'"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Service/decorated_method",
            new_body=new_body,
        )

        content = (tmp_path / "decorated.py").read_text()
        assert "new decorated" in content
        # plain_method should still exist
        assert "def plain_method" in content

    def test_replace_static_method(self, decorated_project):
        """Replace a @staticmethod."""
        tmp_path, idx = decorated_project
        from ii_structure.commands.replace_body import execute

        new_body = "@staticmethod\ndef static_method():\n    return False"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Service/static_method",
            new_body=new_body,
        )

        content = (tmp_path / "decorated.py").read_text()
        assert "return False" in content
        # Other methods intact
        assert "def class_method" in content

    def test_replace_method_with_multiline_strings(self, multiline_string_project):
        """Replace a method that contains triple-quoted strings."""
        tmp_path, idx = multiline_string_project
        from ii_structure.commands.replace_body import execute

        new_body = 'def template(self):\n    return "simple string"'

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Formatter/template",
            new_body=new_body,
        )

        content = (tmp_path / "strings.py").read_text()
        assert '"simple string"' in content
        # The old multiline string should be gone
        assert "Hello {name}" not in content
        # sql_query should still exist
        assert "def sql_query" in content

    def test_replace_with_unicode_content(self, unicode_project):
        """Replace with new unicode content."""
        tmp_path, idx = unicode_project
        from ii_structure.commands.replace_body import execute

        new_body = 'def greet(self, name: str) -> str:\n    return f"Bonjour {name}! 🇫🇷"'

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Greeter/greet",
            new_body=new_body,
        )

        content = (tmp_path / "unicode.py").read_text()
        assert "Bonjour" in content
        assert "🇫🇷" in content
        # Other method intact
        assert "さようなら" in content

    def test_replace_single_line_function(self, single_line_project):
        """Replace a single-line function definition."""
        tmp_path, idx = single_line_project
        from ii_structure.commands.replace_body import execute

        new_body = "def one_liner(): return 99"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="one_liner",
            new_body=new_body,
        )

        content = (tmp_path / "minimal.py").read_text()
        assert "return 99" in content
        assert "return 42" not in content

    def test_replace_expands_symbol(self, single_line_project):
        """Replace a 1-line function with a 5-line function — file grows."""
        tmp_path, idx = single_line_project
        from ii_structure.commands.replace_body import execute

        original_content = (tmp_path / "minimal.py").read_text()
        original_line_count = len(original_content.splitlines())

        new_body = "def two_liner():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z"

        result = execute(
            idx=idx,
            project_root=str(tmp_path),
            name="two_liner",
            new_body=new_body,
        )

        new_content = (tmp_path / "minimal.py").read_text()
        new_line_count = len(new_content.splitlines())

        assert result["lines_removed"] == 2  # was def + return
        assert result["lines_added"] == 5
        assert new_line_count == original_line_count + 3  # grew by 3

    def test_replace_shrinks_symbol(self, indented_input_project):
        """Replace a 2-line method with a 1-line method — file shrinks."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        original_line_count = len((tmp_path / "standard.py").read_text().splitlines())

        new_body = "def add(self, a, b): return a + b"

        result = execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body=new_body,
        )

        new_line_count = len((tmp_path / "standard.py").read_text().splitlines())

        assert result["lines_removed"] == 2
        assert result["lines_added"] == 1
        assert new_line_count == original_line_count - 1

    def test_replace_with_trailing_newlines_in_input(self, indented_input_project):
        """New body has trailing newlines — should not add extra blank lines."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        new_body = "def add(self, a, b):\n    return a + b\n\n\n"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body=new_body,
        )

        content = (tmp_path / "standard.py").read_text()
        # Should still be parseable — check subtract still follows
        assert "def subtract" in content

    def test_replace_whitespace_only_body_errors(self, indented_input_project):
        """Body with only whitespace should be rejected."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        with pytest.raises(ValueError, match="[Ee]mpty"):
            execute(
                idx=idx,
                project_root=str(tmp_path),
                name="Calculator/add",
                new_body="   \n  \n   ",
            )


# ============================================================
# INSERT-SYMBOL: Indentation Tests
# ============================================================

class TestInsertSymbolIndentation:

    def test_insert_into_deeply_nested_class(self, nested_class_project):
        """Insert a method into a 3-level nested class."""
        tmp_path, idx = nested_class_project
        from ii_structure.commands.insert_symbol import execute

        new_code = "def another_deep(self):\n    return 'another'"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="DeepNested/deep_method",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "nested.py").read_text()
        lines = content.splitlines()
        another_line = [line for line in lines if "def another_deep" in line][0]
        # Should be at 12 spaces (same as deep_method)
        assert another_line.startswith("            def another_deep")
        body_line = [line for line in lines if "another" in line and "return" in line][0]
        assert body_line.startswith("                return")

    def test_insert_top_level_after_top_level(self, nested_class_project):
        """Insert a top-level function after another — zero indent."""
        tmp_path, idx = nested_class_project
        from ii_structure.commands.insert_symbol import execute

        new_code = "def another_top():\n    return 'another top'"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="top_level",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "nested.py").read_text()
        lines = content.splitlines()
        another_line = [line for line in lines if "def another_top" in line][0]
        assert another_line == "def another_top():"

    def test_insert_with_already_correct_indentation(self, indented_input_project):
        """New code already at correct indent level."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        # Already indented at 4 spaces (method level)
        new_code = "    def divide(self, a, b):\n        return a / b"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/multiply",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "standard.py").read_text()
        lines = content.splitlines()
        divide_line = [line for line in lines if "def divide" in line][0]
        assert divide_line == "    def divide(self, a, b):"


# ============================================================
# INSERT-SYMBOL: Boundary and Special Cases
# ============================================================

class TestInsertSymbolBoundary:

    def test_insert_before_first_method(self, indented_input_project):
        """Insert before the first method in a class."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        new_code = "def __init__(self):\n    self.value = 0"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/add",
            position="before",
            new_code=new_code,
        )

        content = (tmp_path / "standard.py").read_text()
        lines = content.splitlines()

        init_idx = next(i for i, line in enumerate(lines) if "def __init__" in line)
        add_idx = next(i for i, line in enumerate(lines) if "def add" in line)
        assert init_idx < add_idx

    def test_insert_after_last_method(self, indented_input_project):
        """Insert after the last method in a class."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        new_code = "def divide(self, a, b):\n    return a / b"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/multiply",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "standard.py").read_text()
        assert "def divide" in content
        lines = content.splitlines()
        multiply_idx = next(i for i, line in enumerate(lines) if "def multiply" in line)
        divide_idx = next(i for i, line in enumerate(lines) if "def divide" in line)
        assert divide_idx > multiply_idx

    def test_insert_with_unicode(self, unicode_project):
        """Insert method with unicode content."""
        tmp_path, idx = unicode_project
        from ii_structure.commands.insert_symbol import execute

        new_code = 'def welcome(self) -> str:\n    return "Bienvenue! 🎊"'

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Greeter/farewell",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "unicode.py").read_text()
        assert "Bienvenue! 🎊" in content
        assert "こんにちは" in content  # original still there
        assert "さようなら" in content

    def test_insert_does_not_double_blank_lines(self, indented_input_project):
        """If there's already a blank line between methods, don't add another."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        new_code = "def power(self, a, b):\n    return a ** b"

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/add",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "standard.py").read_text()
        # Should not have triple blank lines anywhere
        assert "\n\n\n" not in content

    def test_insert_multiline_body(self, indented_input_project):
        """Insert a method with many lines."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        new_code = (
            "def complex_method(self, a, b):\n"
            "    result = 0\n"
            "    for i in range(a):\n"
            "        for j in range(b):\n"
            "            result += i * j\n"
            "    return result"
        )

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/add",
            position="after",
            new_code=new_code,
        )

        content = (tmp_path / "standard.py").read_text()
        lines = content.splitlines()

        # Check all indentation levels are correct
        result_line = [line for line in lines if "result = 0" in line][0]
        assert result_line == "        result = 0"  # 8 spaces (method body)

        for_i_line = [line for line in lines if "for i in range" in line][0]
        assert for_i_line == "        for i in range(a):"

        for_j_line = [line for line in lines if "for j in range" in line][0]
        assert for_j_line == "            for j in range(b):"

        inner_line = [line for line in lines if "result += i * j" in line][0]
        assert inner_line == "                result += i * j"

    def test_insert_empty_body_errors(self, indented_input_project):
        """Empty code should be rejected."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        with pytest.raises(ValueError, match="[Ee]mpty"):
            execute(
                idx=idx,
                project_root=str(tmp_path),
                anchor="Calculator/add",
                position="after",
                new_code="",
            )


# ============================================================
# File integrity: verify the ENTIRE file remains valid after edits
# ============================================================

class TestFileIntegrity:

    def test_replace_preserves_rest_of_file(self, nested_class_project):
        """After replacing one method, all other symbols must still parse."""
        tmp_path, idx = nested_class_project
        from ii_structure.commands.replace_body import execute

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Outer/outer_method",
            new_body="def outer_method(self):\n    return 'changed'",
        )

        # Rebuild index — all symbols should still be found
        idx2 = Index.build(tmp_path)
        assert len(idx2.search_symbols("Outer/outer_method")) == 1
        assert len(idx2.search_symbols("Inner/inner_method")) == 1
        assert len(idx2.search_symbols("DeepNested/deep_method")) == 1
        assert len(idx2.search_symbols("top_level")) == 1

    def test_insert_preserves_rest_of_file(self, indented_input_project):
        """After inserting, all original symbols plus the new one must parse."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/add",
            position="after",
            new_code="def power(self, a, b):\n    return a ** b",
        )

        idx2 = Index.build(tmp_path)
        assert len(idx2.search_symbols("Calculator/add")) == 1
        assert len(idx2.search_symbols("Calculator/subtract")) == 1
        assert len(idx2.search_symbols("Calculator/multiply")) == 1
        assert len(idx2.search_symbols("Calculator/power")) == 1

    def test_multiple_sequential_edits(self, indented_input_project):
        """Multiple edits to the same file in sequence should all work."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute as replace_exec
        from ii_structure.commands.insert_symbol import execute as insert_exec

        # Edit 1: replace add
        replace_exec(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body="def add(self, a, b):\n    return a + b + 0",
        )

        # Edit 2: replace subtract (index was refreshed by edit 1)
        replace_exec(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/subtract",
            new_body="def subtract(self, a, b):\n    return a - b - 0",
        )

        # Edit 3: insert a new method
        insert_exec(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/multiply",
            position="after",
            new_code="def divide(self, a, b):\n    return a / b",
        )

        # Verify everything
        content = (tmp_path / "standard.py").read_text()
        assert "a + b + 0" in content
        assert "a - b - 0" in content
        assert "def divide" in content

        idx2 = Index.build(tmp_path)
        assert len(idx2.search_symbols("Calculator/add")) == 1
        assert len(idx2.search_symbols("Calculator/subtract")) == 1
        assert len(idx2.search_symbols("Calculator/multiply")) == 1
        assert len(idx2.search_symbols("Calculator/divide")) == 1

    def test_file_ends_with_newline_after_replace(self, indented_input_project):
        """File should end with a single newline after edits."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.replace_body import execute

        execute(
            idx=idx,
            project_root=str(tmp_path),
            name="Calculator/add",
            new_body="def add(self, a, b):\n    return a + b",
        )

        content = (tmp_path / "standard.py").read_text()
        assert content.endswith("\n")
        assert not content.endswith("\n\n")

    def test_file_ends_with_newline_after_insert(self, indented_input_project):
        """File should end with a single newline after insert."""
        tmp_path, idx = indented_input_project
        from ii_structure.commands.insert_symbol import execute

        execute(
            idx=idx,
            project_root=str(tmp_path),
            anchor="Calculator/multiply",
            position="after",
            new_code="def divide(self, a, b):\n    return a / b",
        )

        content = (tmp_path / "standard.py").read_text()
        assert content.endswith("\n")
