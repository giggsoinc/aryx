"""MCP tool specs for ask-to-visualize (Slice 7).

Two tools, one per step of the backend's own draft/confirm contract
(andie_planner_api.py) — collapsing them would remove the human-confirm
gate the feature exists to provide.
"""
from __future__ import annotations

from mcp import types

_SPEC_ITEM = {
    "type": "object",
    "description": "Pass through EXACTLY what chart_draft returned in "
                   "items.new_kpi / new_analysis / new_visualization — "
                   "the server re-validates, it does not trust this input.",
}


def chart_tool_specs() -> list[types.Tool]:
    """Return the 2 ask-to-visualize tool specs."""
    return [
        types.Tool(
            name="chart_draft",
            description=(
                "Ask-to-visualize, step 1: draft ONE new chart against the "
                "dataset's latest approved spec, from a plain-language "
                "request. Never persists anything — show `preview_text` to "
                "the user, then call chart_confirm only if they approve."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "dataset_id": {"type": "string"},
                    "request_text": {"type": "string",
                                     "description": "What chart the user wants."},
                    "tier": {"type": "string",
                            "description": "LLM tier. Default 'frontier'."},
                },
                "required": ["workspace_id", "dataset_id", "request_text"],
            },
        ),
        types.Tool(
            name="chart_confirm",
            description=(
                "Ask-to-visualize, step 2: re-validate, persist, and chain "
                "execution/composition — the chart appears in the "
                "dashboard after this one call. Pass new_kpi/new_analysis/"
                "new_visualization exactly as returned by chart_draft."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "dataset_id": {"type": "string"},
                    "new_kpi": _SPEC_ITEM,
                    "new_analysis": _SPEC_ITEM,
                    "new_visualization": _SPEC_ITEM,
                },
                "required": ["workspace_id", "dataset_id"],
            },
        ),
    ]
