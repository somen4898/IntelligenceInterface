from ii_structure.backends.typescript import TypeScriptBackend

backend = TypeScriptBackend()

SIMPLE_TS = '''\
import { User } from "./models";

/** Maximum page size. */
export const MAX_PAGE_SIZE = 100;

/** A user in the system. */
export interface UserProfile {
  id: number;
  name: string;
}

/** Base class for services. */
export class BaseService {
  protected db: any;

  constructor(db: any) {
    this.db = db;
  }

  /** Log a message. */
  log(message: string): void {
    console.log(message);
  }
}

/** Format a user for display. */
export function formatUser(user: User): string {
  return `${user.name}`;
}

/** Fetch a user by ID. */
export const getUser = async (id: number): Promise<User | null> => {
  return null;
};

export type UserRole = "admin" | "user";
'''

def test_extracts_function():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    assert result.error is None
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "formatUser" for f in funcs)

def test_extracts_arrow_function():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "getUser" for f in funcs)

def test_extracts_class():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert any(c.name == "BaseService" for c in classes)

def test_extracts_interface():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    ifaces = [s for s in result.symbols if s.kind == "interface"]
    assert any(i.name == "UserProfile" for i in ifaces)

def test_extracts_type_alias():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    types = [s for s in result.symbols if s.kind == "type"]
    assert any(t.name == "UserRole" for t in types)

def test_extracts_variable():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    vars_ = [s for s in result.symbols if s.kind == "variable"]
    assert any(v.name == "MAX_PAGE_SIZE" for v in vars_)

def test_extracts_method():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    methods = [s for s in result.symbols if s.kind == "method"]
    assert any(m.name == "log" for m in methods)
    log = [m for m in methods if m.name == "log"][0]
    assert log.parent == "BaseService"

def test_extracts_imports():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    assert len(result.imports) >= 1
    assert any(i.module == "./models" for i in result.imports)
    assert "User" in result.imports[0].names

def test_extracts_docstring():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    base = [s for s in result.symbols if s.name == "BaseService"][0]
    assert base.docstring is not None
    assert "Base class" in base.docstring

def test_extracts_children():
    result = backend.parse_file("app.ts", SIMPLE_TS)
    base = [s for s in result.symbols if s.name == "BaseService"][0]
    assert "log" in base.children

def test_empty_file():
    result = backend.parse_file("empty.ts", "")
    assert result.error is None
    assert result.symbols == []

def test_tsx_support():
    tsx = 'export const App = () => { return <div>Hello</div>; };'
    result = backend.parse_file("app.tsx", tsx)
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "App" for f in funcs)
