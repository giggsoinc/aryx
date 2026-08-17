"""MCP tool spec for the dashboard link (Slice 5).

One tool. There is no backend endpoint for "give me the dashboard URL" —
/dashboard is a Next.js page keyed by workspace_id, so this tool builds
the URL client-side rather than proxying a call.
"""
from __future__ import annotations

import mcp.types as types


def dashboard_tool_specs() -> list[types.Tool]:
    """Return the 1 dashboard tool spec."""
    return [
        types.Tool(
            name="dashboard_link",
            description=(
                "Return the URL of the rendered dashboard for a workspace. "
                "Pass workspace_id from `list`. Does not check whether a "
                "dashboard has actually been composed yet for that "
                "workspace — the link works once one exists."
            ),
            inputSchema={
                "type": "object",
                "properties": {"workspace_id": {"type": "integer"}},
                "required": ["workspace_id"],
            },
        ),
    ]
