"""Aryx MCP server — stdio + SSE. Wraps REST so any MCP host can drive it."""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from aryx.mcp.tools import tool_specs

logger = logging.getLogger(__name__)

server = Server("aryx")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """MCP handshake hook: advertise every registered tool."""
    return tool_specs()


def _dispatch(name: str, a: dict) -> Any:
    """Route a tool call by exact name or prefix to its dispatch module."""
    if name == "list":
        from aryx.mcp.read import list_workspaces
        return list_workspaces()
    if name == "ask":
        from aryx.mcp.read import ask
        return ask(a)
    if name == "act":
        from aryx.mcp.act import _act
        return _act(a)
    if name.startswith(("workspace_", "brief_")):
        from aryx.mcp.onboard import dispatch as _onboard
        return _onboard(name, a)
    if name.startswith("datasource_"):
        from aryx.mcp.datasource import dispatch as _ds
        return _ds(name, a)
    if name.startswith("ingest_") or name == "entities_preview":
        from aryx.mcp.ingest_hitl import dispatch as _hitl
        return _hitl(name, a)
    if name.startswith("ontology_"):
        from aryx.mcp.ontology import dispatch as _ont
        return _ont(name, a)
    if name == "dashboard_link":
        from aryx.mcp.dashboard import dispatch as _dash
        return _dash(name, a)
    if name.startswith("correction_"):
        from aryx.mcp.correction import dispatch as _corr
        return _corr(name, a)
    if name.startswith("chart_"):
        from aryx.mcp.chart import dispatch as _chart
        return _chart(name, a)
    return {"error": f"unknown tool: {name}"}


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """MCP handshake hook: dispatch and return the result as JSON text —
    never a raw exception, always a structured {"error": ...} instead."""
    try:
        result = _dispatch(name, arguments or {})
    except Exception as exc:  # noqa: BLE001
        result = {"error": str(exc), "tool": name}
    return [types.TextContent(type="text",
            text=json.dumps(result, indent=2, default=str))]


async def main() -> None:
    """Run as a stdio MCP server (for local Claude Desktop)."""
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
