"""Tests for LSP integration with graceful degradation."""
import shutil
import pytest
from ii_structure.index import Index


def test_go_usages_without_gopls(go_project, monkeypatch):
    """Should still return index-based results when gopls is not available."""
    monkeypatch.setattr(shutil, "which", lambda x: None)
    idx = Index.build(go_project)
    from ii_structure.commands.usages import execute
    results = execute(idx=idx, project_root=str(go_project), name="Server")
    # Should return at least the definition
    assert len(results) >= 1
    assert results[0]["kind"] == "definition"


def test_ts_usages_without_tsserver(ts_project, monkeypatch):
    """Should still return index-based results when tsserver is not available."""
    monkeypatch.setattr(shutil, "which", lambda x: None)
    idx = Index.build(ts_project)
    from ii_structure.commands.usages import execute
    results = execute(idx=idx, project_root=str(ts_project), name="User")
    assert len(results) >= 1
    assert results[0]["kind"] == "definition"


@pytest.mark.skipif(not shutil.which("gopls"), reason="gopls not installed")
def test_go_usages_with_gopls(go_project):
    """When gopls is available, should use LSP for references."""
    idx = Index.build(go_project)
    from ii_structure.commands.usages import execute
    results = execute(idx=idx, project_root=str(go_project), name="Server")
    assert len(results) >= 1


@pytest.mark.skipif(not shutil.which("typescript-language-server"), reason="tsserver not installed")
def test_ts_usages_with_tsserver(ts_project):
    """When tsserver is available, should use LSP for references."""
    idx = Index.build(ts_project)
    from ii_structure.commands.usages import execute
    results = execute(idx=idx, project_root=str(ts_project), name="User")
    assert len(results) >= 1
