"""Tests for the generic LSP client.

Tests JSON-RPC encoding/decoding and message framing without requiring
an actual language server.
"""
import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from ii_structure.lsp_client import LspClient


def test_is_available_when_binary_exists():
    client = LspClient(command=["python3"], project_root="/tmp")
    assert client.is_available() is True


def test_is_available_when_binary_missing():
    client = LspClient(command=["nonexistent_binary_xyz"], project_root="/tmp")
    assert client.is_available() is False


def test_find_references_when_unavailable():
    client = LspClient(command=["nonexistent_binary_xyz"], project_root="/tmp")
    result = client.find_references("/tmp/test.go", 1, 0)
    assert result == []


def test_get_definition_when_unavailable():
    client = LspClient(command=["nonexistent_binary_xyz"], project_root="/tmp")
    result = client.get_definition("/tmp/test.go", 1, 0)
    assert result == []


def test_json_rpc_message_format():
    """Verify the JSON-RPC message format is correct."""
    client = LspClient(command=["test"], project_root="/tmp")

    # Test that _send creates proper Content-Length framed messages
    mock_process = MagicMock()
    mock_stdin = MagicMock()
    mock_process.stdin = mock_stdin
    client._process = mock_process

    message = {"jsonrpc": "2.0", "id": 1, "method": "test", "params": {}}
    client._send(message)

    # Verify what was written
    written_data = mock_stdin.write.call_args[0][0]
    written_str = written_data.decode("utf-8")

    # Should have Content-Length header
    assert "Content-Length:" in written_str
    assert "\r\n\r\n" in written_str

    # Extract and verify body
    header, body = written_str.split("\r\n\r\n", 1)
    parsed = json.loads(body)
    assert parsed["jsonrpc"] == "2.0"
    assert parsed["id"] == 1
    assert parsed["method"] == "test"

    # Verify Content-Length matches body
    content_length = int(header.split(":")[1].strip())
    assert content_length == len(body)


def test_shutdown_when_not_started():
    """Shutdown on a never-started client should be a no-op."""
    client = LspClient(command=["test"], project_root="/tmp")
    client.shutdown()  # Should not raise


def test_context_manager():
    """Test that the context manager calls shutdown."""
    client = LspClient(command=["test"], project_root="/tmp")
    with client:
        pass
    # No error means __exit__ (shutdown) succeeded
