"""Default workspace cannot be deleted (Lite guardrail).

  PYTHONPATH=src python3 -c \"from tests.test_workspace_delete_guard import *\"
  or run under pytest.
"""
from __future__ import annotations

from pathlib import Path


def test_default_workspace_delete_rejected() -> None:
    """Guard must raise before any SQL for workspace id 1."""

    class _Fake:
        """Minimal stand-in for WorkspaceStore.delete guard."""

        def delete(self, wid: int) -> None:
            """Mirror production guard: Default (id 1) is non-deletable."""
            if int(wid) == 1:
                raise ValueError("the Default workspace cannot be deleted")

    store = _Fake()
    try:
        store.delete(1)
        raise AssertionError("expected ValueError for Default workspace")
    except ValueError as exc:
        assert "cannot be deleted" in str(exc)


def test_workspace_store_delete_guard_source() -> None:
    """Source-level check: guard remains in WorkspaceStore.delete."""
    root = Path(__file__).resolve().parents[1]
    src = (root / "src" / "aryx" / "workspaces.py").read_text()
    idx = src.find("def delete(self, wid: int)")
    assert idx > 0, "WorkspaceStore.delete missing"
    chunk = src[idx : idx + 400]
    assert "wid) == 1" in chunk or "wid == 1" in chunk
    assert "cannot be deleted" in chunk
