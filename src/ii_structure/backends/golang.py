from __future__ import annotations
import pathlib
import shutil
from tree_sitter_language_pack import get_parser
from ii_structure.parser import SymbolInfo, ImportInfo, ParseResult
from ii_structure.lsp_client import LspClient


class GoBackend:
    def __init__(self):
        self._parser = get_parser("go")

    def parse_file(self, file_path: str, source: str) -> ParseResult:
        if not source.strip():
            return ParseResult(symbols=[], imports=[], error=None)

        tree = self._parser.parse(source)
        root = tree.root_node()

        if root.has_error():
            # Check if it's a meaningful parse or just errors
            symbols, imports = self._extract(root, source)
            if not symbols and not imports:
                return ParseResult(symbols=[], imports=[], error=f"Syntax error in {file_path}")
            return ParseResult(symbols=symbols, imports=imports, error=f"Syntax error in {file_path}")

        symbols, imports = self._extract(root, source)
        return ParseResult(symbols=symbols, imports=imports, error=None)

    def _extract(self, root, source: str) -> tuple[list[SymbolInfo], list[ImportInfo]]:
        symbols: list[SymbolInfo] = []
        imports: list[ImportInfo] = []
        children = _get_children(root)

        # Track preceding comments for docstrings
        prev_comment = None

        for node in children:
            kind = node.kind()

            if kind == "comment":
                prev_comment = _get_text(node, source)
                continue

            if kind == "import_declaration":
                self._extract_imports(node, source, imports)
            elif kind == "function_declaration":
                self._extract_function(node, source, symbols, prev_comment)
            elif kind == "method_declaration":
                self._extract_method(node, source, symbols, prev_comment)
            elif kind == "type_declaration":
                self._extract_type(node, source, symbols, prev_comment)
            elif kind == "var_declaration":
                self._extract_var_const(node, source, symbols, "variable", prev_comment)
            elif kind == "const_declaration":
                self._extract_var_const(node, source, symbols, "variable", prev_comment)

            prev_comment = None

        # Attach methods as children to their receiver types
        self._attach_methods_to_types(symbols)

        return symbols, imports

    def _extract_imports(self, node, source: str, imports: list[ImportInfo]):
        for child in _get_children(node):
            kind = child.kind()
            if kind == "import_spec":
                text = _get_text(child, source).strip().strip('"')
                imports.append(ImportInfo(
                    module=text,
                    names=[],
                    line=child.start_position().row + 1,
                    is_relative=False,
                ))
            elif kind == "import_spec_list":
                for spec in _get_children(child):
                    if spec.kind() == "import_spec":
                        text = _get_text(spec, source).strip().strip('"')
                        imports.append(ImportInfo(
                            module=text,
                            names=[],
                            line=spec.start_position().row + 1,
                            is_relative=False,
                        ))

    def _extract_function(self, node, source: str, symbols: list[SymbolInfo], prev_comment: str | None):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_text(name_node, source)
        signature = _get_text(node, source).split("{")[0].strip()

        symbols.append(SymbolInfo(
            name=name,
            kind="function",
            line=node.start_position().row + 1,
            end_line=node.end_position().row + 1,
            signature=signature,
            docstring=_clean_comment(prev_comment),
            parent=None,
        ))

    def _extract_method(self, node, source: str, symbols: list[SymbolInfo], prev_comment: str | None):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_text(name_node, source)

        # Extract receiver type
        receiver = None
        params = node.child_by_field_name("receiver")
        if params:
            receiver_text = _get_text(params, source)
            # Extract type name from "(s *Server)" or "(s Server)"
            receiver = _extract_receiver_type(receiver_text)

        signature = _get_text(node, source).split("{")[0].strip()

        symbols.append(SymbolInfo(
            name=name,
            kind="method",
            line=node.start_position().row + 1,
            end_line=node.end_position().row + 1,
            signature=signature,
            docstring=_clean_comment(prev_comment),
            parent=receiver,
        ))

    def _extract_type(self, node, source: str, symbols: list[SymbolInfo], prev_comment: str | None):
        for child in _get_children(node):
            if child.kind() == "type_spec":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue
                name = _get_text(name_node, source)

                # Determine if struct or interface
                type_node = child.child_by_field_name("type")
                if type_node:
                    type_kind = type_node.kind()
                    if type_kind == "struct_type":
                        kind = "class"
                        sig = f"type {name} struct"
                    elif type_kind == "interface_type":
                        kind = "interface"
                        sig = f"type {name} interface"
                    else:
                        kind = "type"
                        sig = f"type {name} {_get_text(type_node, source)}"
                else:
                    kind = "type"
                    sig = f"type {name}"

                symbols.append(SymbolInfo(
                    name=name,
                    kind=kind,
                    line=node.start_position().row + 1,
                    end_line=node.end_position().row + 1,
                    signature=sig,
                    docstring=_clean_comment(prev_comment),
                    parent=None,
                ))

    def _extract_var_const(self, node, source: str, symbols: list[SymbolInfo], kind: str, prev_comment: str | None):
        for child in _get_children(node):
            child_kind = child.kind()
            if child_kind in ("var_spec", "const_spec"):
                name_node = child.child_by_field_name("name")
                if not name_node:
                    # Try first identifier child
                    for sub in _get_children(child):
                        if sub.kind() == "identifier":
                            name_node = sub
                            break
                if not name_node:
                    continue
                name = _get_text(name_node, source)
                symbols.append(SymbolInfo(
                    name=name,
                    kind="variable",
                    line=child.start_position().row + 1,
                    end_line=child.end_position().row + 1,
                    signature=_get_text(child, source),
                    docstring=_clean_comment(prev_comment),
                    parent=None,
                ))

    def _attach_methods_to_types(self, symbols: list[SymbolInfo]):
        type_map = {s.name: s for s in symbols if s.kind in ("class", "interface")}
        for s in symbols:
            if s.kind == "method" and s.parent and s.parent in type_map:
                if s.name not in type_map[s.parent].children:
                    type_map[s.parent].children.append(s.name)

    def find_usages(self, project_root, name, index, path_scope=None, kind_filter=None, limit=50, include_tests=True):
        if not shutil.which("gopls"):
            return _index_based_usages(project_root, name, index, path_scope, kind_filter, limit, include_tests)

        # Try LSP-based resolution
        root = pathlib.Path(project_root)
        candidates = index.search_symbols(name)
        if not candidates:
            return []

        try:
            lsp = LspClient(command=["gopls", "serve"], project_root=project_root)
            candidate = candidates[0]
            file_path = str(root / candidate["file"])
            content = pathlib.Path(file_path).read_text(encoding="utf-8", errors="replace")
            lsp.open_document(file_path, content, language_id="go")

            col = _find_name_column(content, candidate["line"], candidate["name"])
            refs = lsp.find_references(file_path, candidate["line"] - 1, col)
            lsp.shutdown()

            if not refs:
                return _index_based_usages(project_root, name, index, path_scope, kind_filter, limit, include_tests)

            results = []
            seen = set()
            for ref in refs:
                try:
                    rel = str(pathlib.Path(ref["file"]).relative_to(root))
                except ValueError:
                    continue
                if path_scope and not rel.startswith(path_scope):
                    continue
                if not include_tests and _is_test_file(rel):
                    continue
                key = (rel, ref["line"])
                if key in seen:
                    continue
                seen.add(key)
                context = _get_context_line(root / rel, ref["line"])
                results.append({
                    "file": rel,
                    "line": ref["line"],
                    "kind": "reference",
                    "context": context,
                })
                if len(results) >= limit:
                    break
            return results
        except Exception:
            return _index_based_usages(project_root, name, index, path_scope, kind_filter, limit, include_tests)

    def get_definition_source(self, project_root, name, index, file_hint=None):
        return _index_based_definition(project_root, name, index, file_hint)


def _get_children(node):
    return [node.child(i) for i in range(node.child_count())]


def _get_text(node, source: str) -> str:
    br = node.byte_range()
    return source[br.start:br.end]


def _clean_comment(comment: str | None) -> str | None:
    if not comment:
        return None
    # Strip "// " prefix
    text = comment.strip()
    if text.startswith("//"):
        text = text[2:].strip()
    return text if text else None


def _extract_receiver_type(receiver_text: str) -> str | None:
    """Extract type name from receiver like '(s *Server)' or '(s Server)'."""
    inner = receiver_text.strip("()")
    parts = inner.split()
    if len(parts) >= 2:
        type_name = parts[-1].lstrip("*")
        return type_name
    elif len(parts) == 1:
        return parts[0].lstrip("*")
    return None


def _find_name_column(source: str, line: int, name: str) -> int:
    lines = source.splitlines()
    if 0 < line <= len(lines):
        idx = lines[line - 1].find(name)
        if idx >= 0:
            return idx
    return 0


def _is_test_file(path: str) -> bool:
    parts = path.split("/")
    filename = parts[-1]
    return filename.endswith("_test.go") or any(p == "test" for p in parts[:-1])


def _get_context_line(file_path: pathlib.Path, line: int) -> str:
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        if 0 < line <= len(lines):
            return lines[line - 1].strip()
    except Exception:
        pass
    return ""


def _index_based_usages(project_root, name, index, path_scope=None, kind_filter=None, limit=50, include_tests=True):
    root = pathlib.Path(project_root)
    candidates = index.search_symbols(name)
    results = []
    for candidate in candidates:
        rel = candidate["file"]
        if path_scope and not rel.startswith(path_scope):
            continue
        if not include_tests and _is_test_file(rel):
            continue
        usage_kind = "definition"
        if kind_filter and usage_kind != kind_filter:
            continue
        context = _get_context_line(root / rel, candidate["line"])
        results.append({
            "file": rel,
            "line": candidate["line"],
            "kind": usage_kind,
            "context": context,
        })
        if len(results) >= limit:
            break
    return results


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
