from ii_structure.backends.golang import GoBackend

backend = GoBackend()

SIMPLE_GO = '''\
// Package main is the entry point.
package main

import (
\t"fmt"
\t"net/http"
)

// Version is the app version.
var Version = "1.0.0"

// MaxRetries controls retry behavior.
const MaxRetries = 3

// Server handles HTTP requests.
type Server struct {
\tAddr string
\tmux  *http.ServeMux
}

// Handler is the interface for handlers.
type Handler interface {
\tServeHTTP(w http.ResponseWriter, r *http.Request)
}

// NewServer creates a new server.
func NewServer(addr string) *Server {
\treturn &Server{Addr: addr}
}

// Start begins listening.
func (s *Server) Start() error {
\treturn http.ListenAndServe(s.Addr, s.mux)
}
'''

def test_extracts_function():
    result = backend.parse_file("main.go", SIMPLE_GO)
    assert result.error is None
    funcs = [s for s in result.symbols if s.kind == "function"]
    assert any(f.name == "NewServer" for f in funcs)
    ns = [f for f in funcs if f.name == "NewServer"][0]
    assert "addr string" in ns.signature
    assert "*Server" in ns.signature

def test_extracts_method():
    result = backend.parse_file("main.go", SIMPLE_GO)
    methods = [s for s in result.symbols if s.kind == "method"]
    assert any(m.name == "Start" for m in methods)
    start = [m for m in methods if m.name == "Start"][0]
    assert start.parent == "Server"

def test_extracts_struct():
    result = backend.parse_file("main.go", SIMPLE_GO)
    classes = [s for s in result.symbols if s.kind == "class"]
    assert any(c.name == "Server" for c in classes)

def test_extracts_interface():
    result = backend.parse_file("main.go", SIMPLE_GO)
    ifaces = [s for s in result.symbols if s.kind == "interface"]
    assert any(i.name == "Handler" for i in ifaces)

def test_extracts_variable():
    result = backend.parse_file("main.go", SIMPLE_GO)
    vars_ = [s for s in result.symbols if s.kind == "variable"]
    names = {v.name for v in vars_}
    assert "Version" in names
    assert "MaxRetries" in names

def test_extracts_imports():
    result = backend.parse_file("main.go", SIMPLE_GO)
    modules = {i.module for i in result.imports}
    assert "fmt" in modules
    assert "net/http" in modules

def test_extracts_docstring():
    result = backend.parse_file("main.go", SIMPLE_GO)
    server = [s for s in result.symbols if s.name == "Server" and s.kind == "class"][0]
    assert server.docstring is not None
    assert "HTTP" in server.docstring

def test_extracts_children():
    result = backend.parse_file("main.go", SIMPLE_GO)
    server = [s for s in result.symbols if s.name == "Server" and s.kind == "class"][0]
    assert "Start" in server.children

def test_empty_file():
    result = backend.parse_file("empty.go", "")
    assert result.error is None
    assert result.symbols == []

def test_syntax_error():
    result = backend.parse_file("bad.go", "func broken(")
    assert result.error is not None

def test_method_signature():
    result = backend.parse_file("main.go", SIMPLE_GO)
    start = [s for s in result.symbols if s.name == "Start"][0]
    assert "func" in start.signature
    assert "error" in start.signature
