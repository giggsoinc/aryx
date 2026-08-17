"""Slice 5 — dashboard_link MCP tool. Pure URL construction, no network."""
from __future__ import annotations

from aryx.mcp.dashboard import dispatch
from aryx.mcp.tools_dashboard import dashboard_tool_specs


def test_specs_include_dashboard_link() -> None:
    names = {t.name for t in dashboard_tool_specs()}
    assert names == {"dashboard_link"}


def test_dispatch_builds_url_from_workspace_id() -> None:
    result = dispatch("dashboard_link", {"workspace_id": 7})
    assert result["workspace_id"] == 7
    assert result["url"].endswith("/dashboard?workspace_id=7")


def test_dispatch_rejects_unknown_tool() -> None:
    result = dispatch("dashboard_zorp", {"workspace_id": 1})
    assert "error" in result
