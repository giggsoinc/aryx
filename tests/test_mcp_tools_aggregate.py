"""Whole-server tool registry: every family aggregates with no collisions."""
from __future__ import annotations

from aryx.mcp.tools import tool_specs


def test_all_tool_names_are_unique() -> None:
    names = [t.name for t in tool_specs()]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"


def test_slices_5_through_7_are_all_registered() -> None:
    names = {t.name for t in tool_specs()}
    assert {"dashboard_link", "ingest_file", "correction_propose",
            "correction_apply", "chart_draft", "chart_confirm"} <= names
