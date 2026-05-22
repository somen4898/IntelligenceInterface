from __future__ import annotations
import pathlib
from tree_sitter_language_pack import get_parser
from ii_structure.parser import SymbolInfo, ImportInfo, EdgeInfo, ParseResult


class TypeScriptBackend:
    def __init__(self):
        self._ts_parser = get_parser("typescript")
        self._tsx_parser = get_parser("tsx")

    def parse_file(self, file_path: str, source: str) -> ParseResult:
        if not source.strip():
            return ParseResult(symbols=[], imports=[], edges=[], error=None)

        parser = self._tsx_parser if file_path.endswith(".tsx") else self._ts_parser
        tree = parser.parse(source)
        root = tree.root_node()

        if root.has_error():
            symbols, imports = self._extract(root, source)
            if not symbols and not imports:
                return ParseResult(symbols=[], imports=[], edges=[], error=f"Syntax error in {file_path}")
            edges = self._extract_edges(root, source, file_path, symbols, imports)
            return ParseResult(symbols=symbols, imports=imports, edges=edges, error=f"Syntax error in {file_path}")

        symbols, imports = self._extract(root, source)
        edges = self._extract_edges(root, source, file_path, symbols, imports)
        return ParseResult(symbols=symbols, imports=imports, edges=edges, error=None)

    def _extract(self, root, source: str) -> tuple[list[SymbolInfo], list[ImportInfo]]:
        symbols: list[SymbolInfo] = []
        imports: list[ImportInfo] = []
        children = _get_children(root)

        prev_comment = None

        for node in children:
            kind = node.kind()

            if kind == "comment":
                text = _get_text(node, source)
                if text.startswith("/**"):
                    prev_comment = text
                continue

            if kind == "import_statement":
                self._extract_import(node, source, imports)
            elif kind == "export_statement":
                self._extract_export(node, source, symbols, imports, prev_comment)
            elif kind == "function_declaration":
                self._extract_function(node, source, symbols, prev_comment)
            elif kind == "class_declaration":
                self._extract_class(node, source, symbols, prev_comment)
            elif kind == "interface_declaration":
                self._extract_interface(node, source, symbols, prev_comment)
            elif kind == "type_alias_declaration":
                self._extract_type_alias(node, source, symbols, prev_comment)
            elif kind == "lexical_declaration":
                self._extract_lexical(node, source, symbols, prev_comment)

            prev_comment = None

        return symbols, imports

    def _extract_export(self, node, source: str, symbols, imports, prev_comment):
        for child in _get_children(node):
            kind = child.kind()
            if kind == "function_declaration":
                self._extract_function(child, source, symbols, prev_comment)
            elif kind == "class_declaration":
                self._extract_class(child, source, symbols, prev_comment)
            elif kind == "interface_declaration":
                self._extract_interface(child, source, symbols, prev_comment)
            elif kind == "type_alias_declaration":
                self._extract_type_alias(child, source, symbols, prev_comment)
            elif kind == "lexical_declaration":
                self._extract_lexical(child, source, symbols, prev_comment)

    def _extract_function(self, node, source: str, symbols, prev_comment):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_text(name_node, source)
        params = node.child_by_field_name("parameters")
        params_text = _get_text(params, source) if params else "()"
        ret_type = node.child_by_field_name("return_type")
        ret_text = _get_text(ret_type, source) if ret_type else ""
        signature = f"function {name}{params_text}{ret_text}"

        symbols.append(SymbolInfo(
            name=name,
            kind="function",
            line=node.start_position().row + 1,
            end_line=node.end_position().row + 1,
            signature=signature,
            docstring=_clean_jsdoc(prev_comment),
            parent=None,
        ))

    def _extract_class(self, node, source: str, symbols, prev_comment):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_text(name_node, source)

        # Check for extends
        heritage = ""
        for child in _get_children(node):
            if child.kind() == "class_heritage":
                heritage = f" {_get_text(child, source)}"
                break

        signature = f"class {name}{heritage}"

        class_symbol = SymbolInfo(
            name=name,
            kind="class",
            line=node.start_position().row + 1,
            end_line=node.end_position().row + 1,
            signature=signature,
            docstring=_clean_jsdoc(prev_comment),
            parent=None,
        )
        symbols.append(class_symbol)

        # Extract methods from class body
        body = node.child_by_field_name("body")
        if body:
            self._extract_class_members(body, source, symbols, name)

    def _extract_class_members(self, body, source: str, symbols, class_name: str):
        prev_comment = None
        for child in _get_children(body):
            kind = child.kind()

            if kind == "comment":
                text = _get_text(child, source)
                if text.startswith("/**"):
                    prev_comment = text
                continue

            if kind == "method_definition":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    prev_comment = None
                    continue
                name = _get_text(name_node, source)
                if name == "constructor":
                    prev_comment = None
                    continue

                params = child.child_by_field_name("parameters")
                params_text = _get_text(params, source) if params else "()"
                ret_type = child.child_by_field_name("return_type")
                ret_text = _get_text(ret_type, source) if ret_type else ""
                signature = f"{name}{params_text}{ret_text}"

                symbols.append(SymbolInfo(
                    name=name,
                    kind="method",
                    line=child.start_position().row + 1,
                    end_line=child.end_position().row + 1,
                    signature=signature,
                    docstring=_clean_jsdoc(prev_comment),
                    parent=class_name,
                ))

                # Add as child of class
                for s in symbols:
                    if s.name == class_name and s.kind == "class":
                        if name not in s.children:
                            s.children.append(name)
                        break

            prev_comment = None

    def _extract_interface(self, node, source: str, symbols, prev_comment):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_text(name_node, source)
        signature = f"interface {name}"

        symbols.append(SymbolInfo(
            name=name,
            kind="interface",
            line=node.start_position().row + 1,
            end_line=node.end_position().row + 1,
            signature=signature,
            docstring=_clean_jsdoc(prev_comment),
            parent=None,
        ))

    def _extract_type_alias(self, node, source: str, symbols, prev_comment):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_text(name_node, source)
        full_text = _get_text(node, source).rstrip(";").strip()
        signature = full_text

        symbols.append(SymbolInfo(
            name=name,
            kind="type",
            line=node.start_position().row + 1,
            end_line=node.end_position().row + 1,
            signature=signature,
            docstring=_clean_jsdoc(prev_comment),
            parent=None,
        ))

    def _extract_lexical(self, node, source: str, symbols, prev_comment):
        for child in _get_children(node):
            if child.kind() == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue
                name = _get_text(name_node, source)
                value_node = child.child_by_field_name("value")

                if value_node and value_node.kind() == "arrow_function":
                    # Arrow function — treat as function
                    arrow_text = _get_text(value_node, source).split("{")[0].strip().rstrip("=>").strip()
                    signature = f"const {name} = {arrow_text}"
                    symbols.append(SymbolInfo(
                        name=name,
                        kind="function",
                        line=node.start_position().row + 1,
                        end_line=node.end_position().row + 1,
                        signature=signature,
                        docstring=_clean_jsdoc(prev_comment),
                        parent=None,
                    ))
                else:
                    # Regular variable
                    symbols.append(SymbolInfo(
                        name=name,
                        kind="variable",
                        line=node.start_position().row + 1,
                        end_line=node.end_position().row + 1,
                        signature=f"{name} = ...",
                        docstring=_clean_jsdoc(prev_comment),
                        parent=None,
                    ))

    def _extract_edges(self, root, source: str, file_path: str, symbols: list[SymbolInfo], imports: list[ImportInfo]) -> list[EdgeInfo]:
        """Extract CALLS and IMPORTS edges from the AST."""
        edges: list[EdgeInfo] = []

        # IMPORTS edges from already-extracted imports
        for imp in imports:
            edges.append(EdgeInfo(
                kind="IMPORTS", source=file_path,
                target=imp.module, file_path=file_path, line=imp.line,
            ))

        # Collect function/method nodes for walking calls
        func_nodes: list[tuple[str, object]] = []
        self._collect_func_nodes(root, source, func_nodes, parent_class=None)

        for qn, node in func_nodes:
            body = node.child_by_field_name("body")
            if not body:
                continue
            self._walk_calls(body, source, file_path, qn, edges)

        return edges

    def _collect_func_nodes(self, root, source: str, result: list, parent_class: str | None):
        """Collect (qualified_name, node) for all function/method declarations."""
        for child in _get_children(root):
            kind = child.kind()
            if kind == "function_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = _get_text(name_node, source)
                    result.append((name, child))
            elif kind == "class_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    class_name = _get_text(name_node, source)
                    body = child.child_by_field_name("body")
                    if body:
                        self._collect_class_methods(body, source, result, class_name)
            elif kind == "export_statement":
                self._collect_func_nodes(child, source, result, parent_class)
            elif kind == "lexical_declaration":
                # Arrow functions: const foo = (...) => { ... }
                for sub in _get_children(child):
                    if sub.kind() == "variable_declarator":
                        name_node = sub.child_by_field_name("name")
                        value_node = sub.child_by_field_name("value")
                        if name_node and value_node and value_node.kind() == "arrow_function":
                            name = _get_text(name_node, source)
                            result.append((name, value_node))

    def _collect_class_methods(self, body, source: str, result: list, class_name: str):
        """Collect methods from a class body."""
        for child in _get_children(body):
            if child.kind() == "method_definition":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = _get_text(name_node, source)
                    if name != "constructor":
                        qn = f"{class_name}.{name}"
                    else:
                        qn = f"{class_name}.{name}"
                    result.append((qn, child))

    def _walk_calls(self, node, source: str, file_path: str, enclosing_qn: str, edges: list[EdgeInfo]):
        """Recursively walk a node's subtree for call/new expressions."""
        for child in _get_children(node):
            kind = child.kind()
            if kind == "call_expression":
                call_name = self._get_call_name(child, source)
                if call_name:
                    edges.append(EdgeInfo(
                        kind="CALLS", source=enclosing_qn,
                        target=call_name, file_path=file_path,
                        line=child.start_position().row + 1,
                    ))
            elif kind == "new_expression":
                call_name = self._get_new_name(child, source)
                if call_name:
                    edges.append(EdgeInfo(
                        kind="CALLS", source=enclosing_qn,
                        target=call_name, file_path=file_path,
                        line=child.start_position().row + 1,
                    ))
            self._walk_calls(child, source, file_path, enclosing_qn, edges)

    def _get_call_name(self, call_node, source: str) -> str | None:
        """Extract function/method name from a call_expression node."""
        func_node = call_node.child_by_field_name("function")
        if not func_node:
            return None
        kind = func_node.kind()
        if kind == "identifier":
            return _get_text(func_node, source)
        if kind == "member_expression":
            prop = func_node.child_by_field_name("property")
            if prop:
                return _get_text(prop, source)
        return None

    def _get_new_name(self, new_node, source: str) -> str | None:
        """Extract constructor name from a new_expression node."""
        constructor = new_node.child_by_field_name("constructor")
        if constructor and constructor.kind() == "identifier":
            return _get_text(constructor, source)
        return None

    def _extract_import(self, node, source: str, imports):
        module = None
        names = []

        for child in _get_children(node):
            if child.kind() == "string":
                module = _get_text(child, source).strip("'\"")
            elif child.kind() == "import_clause":
                for sub in _get_children(child):
                    if sub.kind() == "named_imports":
                        for spec in _get_children(sub):
                            if spec.kind() == "import_specifier":
                                name_node = spec.child_by_field_name("name")
                                if name_node:
                                    names.append(_get_text(name_node, source))
                    elif sub.kind() == "identifier":
                        names.append(_get_text(sub, source))

        if module:
            imports.append(ImportInfo(
                module=module,
                names=names,
                line=node.start_position().row + 1,
                is_relative=module.startswith("."),
            ))

    def get_definition_source(self, project_root, name, index, file_hint=None):
        return _index_based_definition(project_root, name, index, file_hint)


def _get_children(node):
    return [node.child(i) for i in range(node.child_count())]


def _get_text(node, source: str) -> str:
    br = node.byte_range()
    return source[br.start:br.end]


def _clean_jsdoc(comment: str | None) -> str | None:
    if not comment:
        return None
    text = comment.strip()
    if text.startswith("/**") and text.endswith("*/"):
        text = text[3:-2].strip()
        # Remove leading * from each line
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("*"):
                line = line[1:].strip()
            lines.append(line)
        text = " ".join(lines).strip()
    return text if text else None


def _index_based_definition(project_root, name, index, file_hint=None):
    root = pathlib.Path(project_root)
    candidates = index.search_symbols(name)
    if not candidates:
        return None
    if file_hint:
        candidates = [c for c in candidates if c["file"] == file_hint]
        if not candidates:
            return None
    candidate = candidates[0]
    file_path = root / candidate["file"]
    source = file_path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()
    start = candidate["line"] - 1
    end = candidate.get("end_line", candidate["line"])
    body = "\n".join(lines[start:end])
    return {
        "file": candidate["file"],
        "line": candidate["line"],
        "end_line": end,
        "name": candidate["name"],
        "kind": candidate["kind"],
        "source": body,
    }
