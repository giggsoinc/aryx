"""Slice 3 — HITL ingest queue MCP contract test (no live API)."""
from __future__ import annotations

from aryx.mcp.ingest_hitl import dispatch
from aryx.mcp.tools_ingest import ingest_tool_specs


def test_specs_cover_four_tools():
    """The HITL ingest tool surface is exactly 4 tools."""
    names = {t.name for t in ingest_tool_specs()}
    assert names == {"ingest_questions", "ingest_answer",
                     "ingest_status", "entities_preview"}


def test_dispatch_unknown_returns_error():
    """Unknown ingest_* call returns a structured error, never raises."""
    result = dispatch("ingest_zorp", {"workspace_id": 1})
    assert "error" in result and "ingest_zorp" in result["error"]


def test_all_slices_register_under_one_tool_specs():
    """tool_specs() returns the union of every slice's specs (16 total)."""
    from aryx.mcp.tools import tool_specs
    names = {t.name for t in tool_specs()}
    expected_new = {
        "workspace_list", "workspace_create", "workspace_select",
        "brief_get", "brief_draft", "brief_set", "brief_save",
        "datasource_quiz", "datasource_add", "datasource_list",
        "datasource_test", "datasource_delete",
        "ingest_questions", "ingest_answer", "ingest_status",
        "entities_preview",
    }
    assert expected_new <= names
    assert {"list", "ask", "act"} <= names
