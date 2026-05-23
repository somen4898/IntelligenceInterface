import ast
from dataclasses import dataclass, field

_MAX_AST_DEPTH = 180


@dataclass
class SymbolInfo:
    name: str
    kind: str  # "class", "function", "method", "variable"
    line: int
    end_line: int
    signature: str
    docstring: str | None
    parent: str | None
    children: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    line: int
    is_relative: bool


@dataclass
class EdgeInfo:
    kind: str       # CALLS, IMPORTS, TESTED_BY
    source: str     # qualified name of caller
    target: str     # qualified name or bare name of callee
    file_path: str
    line: int = 0


@dataclass
class ParseResult:
    symbols: list[SymbolInfo]
    imports: list[ImportInfo]
    edges: list[EdgeInfo]
    error: str | None


def parse_file(file_path: str, source: str) -> ParseResult:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return ParseResult(symbols=[], imports=[], edges=[], error=str(e))

    symbols: list[SymbolInfo] = []
    imports: list[ImportInfo] = []
    edges: list[EdgeInfo] = []

    _extract_symbols(tree, symbols, parent_path=None)
    _extract_imports(tree, imports)
    _extract_edges(tree, file_path, edges, symbols)

    return ParseResult(symbols=symbols, imports=imports, edges=edges, error=None)


def _extract_symbols(
    node: ast.AST,
    symbols: list[SymbolInfo],
    parent_path: str | None,
    _depth: int = 0,
) -> None:
    if _depth > _MAX_AST_DEPTH:
        return
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            info = _make_class_info(child, parent_path)
            symbols.append(info)
            child_path = f"{parent_path}/{child.name}" if parent_path else child.name
            _extract_symbols(child, symbols, parent_path=child_path, _depth=_depth + 1)

        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info = _make_function_info(child, parent_path)
            symbols.append(info)
            # Record as child of parent class
            if parent_path is not None:
                for s in symbols:
                    if _path_matches(s, parent_path):
                        if child.name not in s.children:
                            s.children.append(child.name)
                        break

        elif isinstance(child, ast.Assign):
            # Only extract module-level variables (parent_path is None)
            if parent_path is None:
                _extract_assign(child, symbols, parent_path)

        elif isinstance(child, ast.AnnAssign):
            # Only extract module-level annotated variables (parent_path is None)
            if parent_path is None:
                _extract_ann_assign(child, symbols, parent_path)


def _path_matches(symbol: SymbolInfo, parent_path: str) -> bool:
    if "/" not in parent_path:
        return symbol.parent is None and symbol.name == parent_path
    parts = parent_path.split("/")
    # The symbol name must match the last part and its parent must match the rest
    expected_parent = "/".join(parts[:-1])
    return symbol.name == parts[-1] and symbol.parent == expected_parent


def _make_class_info(node: ast.ClassDef, parent_path: str | None) -> SymbolInfo:
    bases = [ast.unparse(b) for b in node.bases]
    base_str = f"({', '.join(bases)})" if bases else ""
    signature = f"class {node.name}{base_str}"
    decorators = [ast.unparse(d) for d in node.decorator_list]
    if decorators:
        signature = f"@{', @'.join(decorators)}\n{signature}"

    return SymbolInfo(
        name=node.name,
        kind="class",
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        signature=signature,
        docstring=_get_docstring(node),
        parent=parent_path,
        children=[],
        decorators=decorators,
    )


def _make_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent_path: str | None,
) -> SymbolInfo:
    kind = "method" if parent_path is not None else "function"
    is_async = isinstance(node, ast.AsyncFunctionDef)

    args_str = _format_args(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if is_async else "def"
    signature = f"{prefix} {node.name}({args_str}){returns}"

    decorators = [ast.unparse(d) for d in node.decorator_list]

    return SymbolInfo(
        name=node.name,
        kind=kind,
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        signature=signature,
        docstring=_get_docstring(node),
        parent=parent_path,
        children=[],
        decorators=decorators,
    )


def _format_args(args: ast.arguments) -> str:
    parts = []
    num_args = len(args.args)
    num_defaults = len(args.defaults)
    non_default_count = num_args - num_defaults

    for i, arg in enumerate(args.args):
        s = arg.arg
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        default_idx = i - non_default_count
        if default_idx >= 0:
            s += f" = {ast.unparse(args.defaults[default_idx])}"
        parts.append(s)

    if args.vararg:
        s = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            s += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(s)

    for i, arg in enumerate(args.kwonlyargs):
        s = arg.arg
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            s += f" = {ast.unparse(args.kw_defaults[i])}"
        parts.append(s)

    if args.kwarg:
        s = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            s += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(s)

    return ", ".join(parts)


def _extract_assign(
    node: ast.Assign,
    symbols: list[SymbolInfo],
    parent_path: str | None,
) -> None:
    for target in node.targets:
        if isinstance(target, ast.Name):
            symbols.append(SymbolInfo(
                name=target.id,
                kind="variable",
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=f"{target.id} = ...",
                docstring=None,
                parent=parent_path,
            ))


def _extract_ann_assign(
    node: ast.AnnAssign,
    symbols: list[SymbolInfo],
    parent_path: str | None,
) -> None:
    if isinstance(node.target, ast.Name):
        annotation = ast.unparse(node.annotation)
        symbols.append(SymbolInfo(
            name=node.target.id,
            kind="variable",
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=f"{node.target.id}: {annotation}",
            docstring=None,
            parent=parent_path,
        ))


def _get_docstring(node: ast.AST) -> str | None:
    if not hasattr(node, "body") or not node.body:
        return None
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        doc = first.value.value.strip()
        if len(doc) > 200:
            return doc[:200] + "..."
        return doc
    return None


def _extract_imports(tree: ast.Module, imports: list[ImportInfo]) -> None:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=[],
                    line=node.lineno,
                    is_relative=False,
                ))
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names] if node.names else []
            imports.append(ImportInfo(
                module=node.module or "",
                names=names,
                line=node.lineno,
                is_relative=(node.level or 0) > 0,
            ))


def _is_test_file_path(file_path: str) -> bool:
    name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    return name.startswith("test_") or name.endswith("_test.py")


def _extract_edges(tree: ast.Module, file_path: str, edges: list[EdgeInfo], symbols: list[SymbolInfo] | None = None) -> None:
    is_test = _is_test_file_path(file_path)

    # Build same-file resolution lookup from already-extracted symbols
    defined_names: dict[str, str] = {}
    if symbols:
        for sym in symbols:
            if sym.kind in ("function", "method", "class"):
                if sym.parent:
                    qn = f"{file_path}::{sym.parent}.{sym.name}"
                else:
                    qn = f"{file_path}::{sym.name}"
                defined_names[sym.name] = qn

    # IMPORTS edges
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(EdgeInfo(
                    kind="IMPORTS", source=file_path,
                    target=alias.name, file_path=file_path, line=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                edges.append(EdgeInfo(
                    kind="IMPORTS", source=file_path,
                    target=node.module, file_path=file_path, line=node.lineno,
                ))

    # Walk all functions/methods for CALLS/TESTED_BY edges
    _extract_calls_recursive(tree, file_path, edges, is_test, parent_class=None, defined_names=defined_names)


def _extract_calls_recursive(node, file_path, edges, is_test_file, parent_class=None, defined_names=None, _depth=0):
    if _depth > _MAX_AST_DEPTH:
        return
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            _extract_calls_recursive(child, file_path, edges, is_test_file, parent_class=child.name, defined_names=defined_names, _depth=_depth + 1)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Build source qualified name
            if parent_class:
                source_qn = f"{file_path}::{parent_class}.{child.name}"
            else:
                source_qn = f"{file_path}::{child.name}"

            is_test_func = child.name.startswith("test_")
            edge_kind = "TESTED_BY" if (is_test_file and is_test_func) else "CALLS"

            # Walk the function body for Call nodes
            for inner_node in ast.walk(child):
                if isinstance(inner_node, ast.Call):
                    call_name = _get_call_name(inner_node)
                    if call_name:
                        # Resolve to qualified name if defined in same file
                        target = defined_names.get(call_name, call_name) if defined_names else call_name
                        edges.append(EdgeInfo(
                            kind=edge_kind,
                            source=source_qn,
                            target=target,
                            file_path=file_path,
                            line=inner_node.lineno,
                        ))


def _get_call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None
