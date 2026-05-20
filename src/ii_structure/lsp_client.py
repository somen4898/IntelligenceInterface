"""Generic LSP client for language server integration.

Minimal JSON-RPC over stdio client that supports:
- initialize/shutdown lifecycle
- textDocument/didOpen
- textDocument/references
- textDocument/definition
"""
from __future__ import annotations
import json
import shutil
import subprocess
import threading
from pathlib import Path


class LspClient:
    def __init__(self, command: list[str], project_root: str):
        self._command = command
        self._project_root = project_root
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Check if the server binary exists on PATH."""
        return shutil.which(self._command[0]) is not None

    def _start(self):
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._project_root,
        )
        self._initialize()

    def _initialize(self):
        result = self._request("initialize", {
            "processId": None,
            "rootUri": f"file://{self._project_root}",
            "capabilities": {},
        })
        self._notify("initialized", {})
        return result

    def open_document(self, file_path: str, content: str, language_id: str = ""):
        uri = f"file://{file_path}"
        self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": content,
            }
        })

    def find_references(self, file_path: str, line: int, column: int) -> list[dict]:
        """Find all references to symbol at position. Returns [{file, line, column}]."""
        if not self.is_available():
            return []

        self._start()
        uri = f"file://{file_path}"
        result = self._request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
            "context": {"includeDeclaration": True},
        })

        if not result:
            return []

        refs = []
        for loc in result:
            loc_uri = loc.get("uri", "")
            loc_range = loc.get("range", {}).get("start", {})
            if loc_uri.startswith("file://"):
                refs.append({
                    "file": loc_uri[7:],  # strip file://
                    "line": loc_range.get("line", 0) + 1,  # 0-indexed -> 1-indexed
                    "column": loc_range.get("character", 0),
                })
        return refs

    def get_definition(self, file_path: str, line: int, column: int) -> list[dict]:
        """Get definition location(s) for symbol at position."""
        if not self.is_available():
            return []

        self._start()
        uri = f"file://{file_path}"
        result = self._request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": column},
        })

        if not result:
            return []

        # Result can be a single Location or a list
        if isinstance(result, dict):
            result = [result]

        defs = []
        for loc in result:
            loc_uri = loc.get("uri", "")
            loc_range = loc.get("range", {}).get("start", {})
            if loc_uri.startswith("file://"):
                defs.append({
                    "file": loc_uri[7:],
                    "line": loc_range.get("line", 0) + 1,
                    "column": loc_range.get("character", 0),
                })
        return defs

    def shutdown(self):
        """Cleanly shut down the server."""
        if self._process is None:
            return
        try:
            self._request("shutdown", None)
            self._notify("exit", None)
            self._process.wait(timeout=5)
        except Exception:
            self._process.kill()
        finally:
            self._process = None

    def _request(self, method: str, params):
        with self._lock:
            self._request_id += 1
            msg_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
        self._send(message)
        return self._receive(msg_id)

    def _notify(self, method: str, params):
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._send(message)

    def _send(self, message: dict):
        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        data = (header + body).encode("utf-8")
        self._process.stdin.write(data)
        self._process.stdin.flush()

    def _receive(self, expected_id: int, timeout: float = 30.0):
        """Read responses until we get the one matching expected_id."""
        import select
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Read Content-Length header
            header_line = b""
            while True:
                byte = self._process.stdout.read(1)
                if not byte:
                    return None
                header_line += byte
                if header_line.endswith(b"\r\n\r\n"):
                    break

            # Parse content length
            header_str = header_line.decode("utf-8")
            content_length = None
            for line in header_str.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":")[1].strip())
                    break

            if content_length is None:
                return None

            # Read body
            body = self._process.stdout.read(content_length)
            response = json.loads(body.decode("utf-8"))

            # Skip notifications (no id)
            if "id" not in response:
                continue

            if response.get("id") == expected_id:
                return response.get("result")

        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()
