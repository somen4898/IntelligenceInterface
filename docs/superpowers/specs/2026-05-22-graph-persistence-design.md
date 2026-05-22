# Graph Persistence & Blast Radius — Design Spec

**Date:** 2026-05-22
**Status:** Draft
**Scope:** Replace JSON index with SQLite graph store, add edge extraction, add blast-radius/dead-code/test-coverage commands, simplify usages/imports, remove dead code.

---

## Problem

ii-structure stores symbols in a flat JSON index — no relationships. Agents can ask "where is `User/save`?" but not "what breaks if I change `User/save`?" The `usages` command requires live LSP calls (~1-3s each), and `imports` uses 7 helper functions to reconstruct dependency graphs at query time. Both are slow, complex, and could be instant with pre-computed edges.

## Solution

Migrate from JSON index to SQLite. Store nodes (symbols) AND edges (calls, imports, test coverage). Extract edges from AST at build time. New commands: `blast-radius`, `dead-code`, `test-coverage`. Rewrite `usages` and `imports` as edge queries. Remove dead code from resolver and import helpers.

---

## Architecture

### Storage: `.ii-structure/graph.db` (SQLite)

Replaces `.ii-structure/index.json`.

```sql
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- class, function, method, variable
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL UNIQUE,  -- "file.py::Parent.name"
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    signature TEXT,
    docstring TEXT,
    parent_name TEXT,
    decorators TEXT,                 -- JSON array
    children TEXT,                   -- JSON array
    file_hash TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- CALLS, IMPORTS, TESTED_BY
    source_qualified TEXT NOT NULL,
    target_qualified TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX idx_nodes_file ON nodes(file_path);
CREATE INDEX idx_nodes_kind ON nodes(kind);
CREATE INDEX idx_nodes_qualified ON nodes(qualified_name);
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_edges_source ON edges(source_qualified);
CREATE INDEX idx_edges_target ON edges(target_qualified);
CREATE INDEX idx_edges_kind ON edges(kind);
CREATE INDEX idx_edges_file ON edges(file_path);
```

**SQLite pragmas:**
- `journal_mode=WAL` — concurrent reads during writes
- `busy_timeout=5000` — wait on lock instead of erroring
- `check_same_thread=False` — safe for stateless CLI
- `isolation_level=None` — explicit transaction control

**Qualified name format:** `file_path::Parent.name` (e.g. `src/models/user.py::User.save`). Globally unambiguous.

**Edge kinds (3):**
- `CALLS` — function A calls function B
- `IMPORTS` — file A imports symbol from file B
- `TESTED_BY` — test function covers a symbol

**Schema versioning:** `metadata` table stores `schema_version`. Migration runner checks version on open and runs pending migrations.

**Name sanitization:** Strip ASCII control chars, cap at 256 characters. Prevents prompt injection via adversarial symbol names in source code.

### GraphStore class (~300 lines)

New file: `src/ii_structure/graph.py`

**Lifecycle:**
- `__init__(db_path)` — open SQLite, set pragmas, init schema, run migrations
- `close()` — commit + close
- `__enter__` / `__exit__` — context manager

**Write operations:**
- `upsert_node(node)` — INSERT ON CONFLICT UPDATE by qualified_name
- `upsert_edge(edge)` — INSERT or UPDATE by (kind, source, target, file, line)
- `remove_file_data(file_path)` — DELETE all nodes/edges for a file
- `store_file_nodes_edges(file_path, nodes, edges, file_hash)` — BEGIN IMMEDIATE → remove old → insert new → COMMIT (atomic per-file replace)
- `commit()` — explicit commit

**Read operations:**
- `get_node(qualified_name)` — single node lookup
- `get_nodes_by_file(file_path)` — all symbols in a file
- `search_nodes(query, limit)` — LIKE substring search on name/qualified_name/docstring, then score in Python with existing `_score_match` logic
- `get_edges_by_source(qualified_name)` — outgoing edges (what does X call?)
- `get_edges_by_target(qualified_name)` — incoming edges (who calls X?)
- `get_callers(qualified_name)` — convenience: incoming CALLS edges with joined node data
- `get_file_imports(file_path, depth)` — recursive CTE for IMPORTS edges at depth N
- `get_all_files()` — distinct file paths
- `get_stats()` — node/edge counts

**Analysis operations:**
- `get_impact_radius(qualified_name, max_depth, max_nodes)` — recursive CTE for blast radius (adapted from code-review-graph's proven SQL)
- `get_dead_symbols(file_path=None)` — nodes with zero incoming CALLS edges, excluding tests/init/main
- `get_transitive_tests(qualified_name, max_depth)` — direct TESTED_BY + follow CALLS edges for indirect coverage
- `resolve_bare_call_targets()` — post-processing pass to match bare call names against global node table, disambiguate via IMPORTS edges

**Blast radius SQL (from code-review-graph, proven):**
```sql
WITH RECURSIVE impacted(node_qn, depth) AS (
    SELECT qn, 0 FROM _impact_seeds
    UNION
    SELECT e.target_qualified, i.depth + 1
    FROM impacted i JOIN edges e ON e.source_qualified = i.node_qn
    WHERE i.depth < ?
    UNION
    SELECT e.source_qualified, i.depth + 1
    FROM impacted i JOIN edges e ON e.target_qualified = i.node_qn
    WHERE i.depth < ?
)
SELECT DISTINCT node_qn, MIN(depth) AS min_depth
FROM impacted GROUP BY node_qn LIMIT ?
```

### Edge Extraction

Extend existing parsers to emit `EdgeInfo` alongside `SymbolInfo`.

**New data structures in `parser.py`:**
```python
@dataclass
class EdgeInfo:
    kind: str       # CALLS, IMPORTS, TESTED_BY
    source: str     # qualified name of caller
    target: str     # qualified name or bare name of callee
    file_path: str
    line: int = 0
```

`ParseResult` gains a new field:
```python
@dataclass
class ParseResult:
    symbols: list[SymbolInfo]
    imports: list[ImportInfo]
    edges: list[EdgeInfo]      # NEW
    error: str | None
```

**Per-language extraction:**

| Language | AST call node type | Parser file |
|---|---|---|
| Python | `ast.Call` (Name, Attribute) | `parser.py` |
| Go | `call_expression` (tree-sitter) | `backends/golang.py` |
| TypeScript | `call_expression`, `new_expression` (tree-sitter) | `backends/typescript.py` |

**Call extraction logic (all languages):**
1. Walk AST inside each function/method body
2. For each call expression, extract the call name
3. Determine the caller (enclosing function qualified name)
4. Try to resolve target via import map + local definitions
5. If unresolved, store bare name (resolved in post-processing)

**IMPORTS edges:** Converted from existing `ImportInfo` records. Each `from module import name` becomes an edge from the file to the resolved target file/symbol.

**TESTED_BY edges:** If a function in a test file (detected via existing `_is_test_file()`) calls symbol X, emit `EdgeInfo(kind="TESTED_BY", source=test_func, target=X)`.

### Index class migration

`Index` class in `index.py` becomes a thin wrapper around `GraphStore`:

- `Index.build(root)` → parse all files, extract nodes + edges, store in `graph.db`
- `Index.load(state_dir)` → open existing `graph.db`
- `Index.refresh(root)` → incremental update (detect changed files, re-parse + update edges)
- `Index.search_symbols(name_path)` → SQL query on nodes table
- `Index.get_symbols(rel_path)` → SQL query by file_path
- `Index.all_symbols()` → SQL query all nodes
- `Index.save(state_dir)` → `graph.commit()` (no more JSON serialization)

The public API stays the same — existing commands that use `idx.search_symbols()` continue to work without modification to their call sites.

### Write command improvements

After `replace-body` or `insert-symbol`:
1. Re-parse changed file → extract new nodes + edges (~50ms)
2. Atomic replace in SQLite via `store_file_nodes_edges` (~5ms)
3. If symbol signature changed: find dependent files via IMPORTS edges, re-parse those too (~100ms for 2-3 files)
4. Run `resolve_bare_call_targets()` if new edges were added
5. `usages`, `imports`, `blast-radius` immediately correct after writes

Optimization: compare old and new node signatures before triggering dependent re-parse. Body-only changes don't affect dependents.

---

## Command changes

### Rewritten commands

**`usages`** — drops live LSP dispatch, becomes an edge query:
```sql
SELECT e.source_qualified, e.line, n.file_path, n.kind
FROM edges e JOIN nodes n ON e.source_qualified = n.qualified_name
WHERE e.target_qualified = ? AND e.kind = 'CALLS'
```
Flags `--path`, `--kind`, `--limit`, `--no-tests` filter the SQL results.
Backend `find_usages()` methods remain available for optional LSP-enhanced edge building at build time but are not called at query time.

**`imports`** — drops 7 helper functions, becomes an edge query:
```sql
-- Forward
SELECT target_qualified FROM edges WHERE kind='IMPORTS' AND file_path = ?
-- Reverse
SELECT file_path FROM edges WHERE kind='IMPORTS' AND target_qualified LIKE ?
```
For `--depth > 1`, uses recursive CTE.

### New commands

**`blast-radius <symbol> [--depth N] [--file FILE]`**
- Runs `get_impact_radius` recursive CTE from the symbol
- Returns flat list: symbol, file, depth, relationship kind (calls/imports/tests)
- Includes test coverage info: which affected paths have tests, which don't
- Default depth: 3, max: 10

**`dead-code [--file FILE] [--kind function|method|class]`**
- Queries nodes with zero incoming CALLS edges
- Filters out: test functions, `__init__`, `__main__`, `main`, decorated entry points (`@app.route`, `@cli.command`)
- Returns list with symbol, file, line, kind

**`test-coverage <symbol> [--depth N]`**
- Direct TESTED_BY edges on the symbol
- Indirect: follow CALLS edges from the symbol, collect TESTED_BY on callees
- Returns: list of covering tests (direct/indirect flag), uncovered callers
- Bare-name fallback for tests that reference symbols without full qualification

### Improved commands (no API change)

**`locate`** — SQL indexed lookup instead of O(N) scan
**`body`** — faster node resolution via SQL index
**`search`** — SQL pre-filter + existing `_score_match` ranking
**`files`** — `SELECT DISTINCT file_path FROM nodes`
**`outline`** — `SELECT * FROM nodes WHERE file_path = ?`

### Unchanged commands

**`help`** — reads YAML, no index interaction
**`replace-body`** — same API, better post-write refresh (edges updated)
**`insert-symbol`** — same API, better post-write refresh

---

## Dead code removal

Code that becomes unnecessary after migration:

**`resolver.py`:**
- `find_usages()` — replaced by edge query (keep `get_definition_source()` for `body` command's source reading, or move source reading into body.py directly)
- `_classify_reference()` — only used by `find_usages()`
- `_find_name_column()` — only used by `find_usages()` for Jedi column positioning
- `_get_context_line()` — only used by `find_usages()`
- `_is_test_file()` — move to a shared utility if needed by edge extraction

**`commands/imports.py` helper functions:**
- `_get_imports()` — replaced by IMPORTS edge query
- `_get_importers()` — replaced by reverse IMPORTS edge query
- `_file_imports()` — replaced by edge existence check
- `_resolve_module()` — moves to build-time edge extraction
- `_module_matches_file()` — moves to build-time edge extraction
- `_file_to_module()` — moves to build-time edge extraction

**`commands/usages.py`:**
- Backend dispatch logic (`get_backend`, language-specific routing) — replaced by single SQL query

**Backend `find_usages()` methods:**
- `backends/python.py` PythonBackend.find_usages — wrapper around resolver
- `backends/golang.py` GoBackend.find_usages — LSP-based
- `backends/typescript.py` TypeScriptBackend.find_usages — LSP-based
- These can optionally be kept for LSP-enhanced build mode but are not used at query time

**`LanguageBackend` Protocol:**
- `find_usages` method can be removed from the Protocol since it's no longer called at query time
- `get_definition_source` — keep on backends (still needed by `body` to read source from disk), but remove from the Protocol requirement since it's backend-internal

---

## Migration strategy

**Auto-migration on first run:**
1. If `index.json` exists and `graph.db` does not → full rebuild with edge extraction → delete `index.json`
2. If both exist → trust `graph.db`, delete `index.json`
3. If neither exists → full build into `graph.db`

**Backward compatibility:** None needed. The JSON format is internal — no external consumers. The `Index` class public API stays the same.

**Schema versioning:** `metadata` table with `schema_version`. Migration runner on open. Adapted from code-review-graph's pattern.

---

## Performance targets

| Operation | Current | Target |
|---|---|---|
| Full build (500 files) | ~2s (symbols only) | ~5-7s (symbols + edges) |
| Incremental update (1 file changed) | ~100ms | ~200ms (+ dependents) |
| `usages` query | 1-3s (live LSP) | <10ms (SQL) |
| `imports` query | ~50ms (7-function chain) | <10ms (SQL) |
| `blast-radius` query | N/A | <50ms (recursive CTE) |
| `dead-code` query | N/A | <10ms (SQL) |
| `locate` query | ~5ms (in-memory scan) | <1ms (SQL index) |
| Post-write refresh | ~70ms (parse + write JSON) | ~200ms (parse + edges + dependents) |

---

## Testing strategy

**GraphStore unit tests:**
- CRUD: upsert_node, upsert_edge, remove_file_data, store_file_nodes_edges
- Queries: get_node, get_nodes_by_file, search_nodes, get_edges_by_source/target
- Blast radius: linear chain (A→B→C), diamond (A→B,C→D), cycle detection, depth limit
- Dead code: symbol with no callers detected, symbol with callers excluded
- Test coverage: direct TESTED_BY, transitive via CALLS, bare-name fallback
- Bare call resolution: single candidate resolves, ambiguous left bare, import-based disambiguation
- Edge cases: empty graph, single node, self-referencing edges, circular dependencies

**Edge extraction tests (per language):**
- Python: function calls, method calls (`self.x()`), imported calls, nested calls, decorator calls
- Go: function calls, method calls (receiver.Method()), package-qualified calls
- TypeScript: function calls, method calls, `new` expressions, imported calls
- All: test file detection, TESTED_BY edge generation

**Integration tests:**
- Parse project → build graph → query blast-radius → verify propagation
- Edit symbol → verify edges refreshed → query usages → verify correct
- Sequential edits → graph stays consistent

**Migration tests:**
- Project with existing index.json → migrate → verify all symbols present in graph.db
- Project with no index → fresh build → verify graph.db created

**Regression:**
- All 241 existing tests must pass
- Command output shapes unchanged (YAML envelope, same fields)

---

## README & Benchmarks

**README.md:** Complete rewrite. The current README describes a read-only + basic write tool. The new README needs to reflect:
- Graph-backed architecture (SQLite, not JSON)
- Edge relationships (calls, imports, test coverage)
- 3 new commands (blast-radius, dead-code, test-coverage)
- Rewritten usages/imports (instant, not LSP-dependent)
- Updated token savings benchmarks
- Updated architecture diagrams / flow descriptions
- Safe write workflow with edge refresh

**Benchmarks:** Re-run on user-provided codebases to measure:
- Token savings: ii-structure with edges vs native tools (should improve over current 14.6x due to instant usages)
- Build time: full build with edge extraction vs without
- Query time: usages/imports before (LSP) vs after (SQLite)
- Blast-radius value: demonstrate what the agent learns from one blast-radius call vs multiple usages + imports chains

---

## New dependencies

None. SQLite is in Python stdlib (`sqlite3`). No new pip packages.

---

## Files changed

| File | Change |
|---|---|
| `src/ii_structure/graph.py` | NEW — GraphStore class (~300 lines) |
| `src/ii_structure/parser.py` | ADD EdgeInfo dataclass, add edge extraction to parse_file |
| `src/ii_structure/backends/golang.py` | ADD edge extraction to parse_file |
| `src/ii_structure/backends/typescript.py` | ADD edge extraction to parse_file |
| `src/ii_structure/index.py` | REWRITE — thin wrapper around GraphStore |
| `src/ii_structure/commands/usages.py` | REWRITE — SQL edge query |
| `src/ii_structure/commands/imports.py` | REWRITE — SQL edge query, remove 7 helpers |
| `src/ii_structure/commands/blast_radius.py` | NEW |
| `src/ii_structure/commands/dead_code.py` | NEW |
| `src/ii_structure/commands/test_coverage.py` | NEW |
| `src/ii_structure/commands/body.py` | MINOR — use GraphStore for node lookup |
| `src/ii_structure/commands/replace_body.py` | MINOR — refresh edges after write |
| `src/ii_structure/commands/insert_symbol.py` | MINOR — refresh edges after write |
| `src/ii_structure/cli.py` | ADD 3 new Click commands, update help |
| `src/ii_structure/resolver.py` | REMOVE dead functions (find_usages, helpers) |
| `src/ii_structure/backends/base.py` | REMOVE find_usages from Protocol |
| `src/ii_structure/help_content.yaml` | ADD entries for 3 new commands |
| `README.md` | UPDATE command tables, architecture description |
