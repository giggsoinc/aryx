"""Aryx MCP server (Inc 11+) — stdio + SSE, read-only, 8 tools.

Wraps the live Aryx REST API so any MCP-compatible agent (Claude Desktop,
Claude Code, Cursor, Continue) can query the knowledge graph.
Set ARYX_API_URL to point at the running API instance.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from aryx.mcp.tools import tool_specs

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")
_DEFAULT_WS = int(os.environ.get("ARYX_MCP_DEFAULT_WORKSPACE", "1"))
_POST_TIMEOUT = int(os.environ.get("ARYX_MCP_POST_TIMEOUT", "50"))
server = Server("aryx")

_WRITE_RX = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|DETACH)\b", re.IGNORECASE
)


def _ws(args: dict[str, Any]) -> int:
    """Resolve workspace_id from args or env default."""
    return int(args.get("workspace_id") or _DEFAULT_WS)


def _qs(args: dict[str, Any], extras: dict[str, Any]) -> str:
    """Build a query string merging tool args + extras (workspace_id first)."""
    out = [f"workspace_id={_ws(args)}"]
    for k, v in extras.items():
        if v is not None and v != "":
            out.append(f"{k}={urllib.parse.quote(str(v))}")
    return "?" + "&".join(out)


def _get(path: str) -> Any:
    url = f"{_API_URL}{path}"
    with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def _post(path: str, body: dict) -> Any:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_API_URL}{path}", data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_POST_TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the static tool specs."""
    return tool_specs()


def _dispatch(name: str, a: dict) -> Any:
    """Route a tool call to the right REST endpoint."""
    if name == "list_workspaces":
        return _get("/admin/workspaces?workspace_id=1")
    if name == "list_types":
        return _get("/ontology/types" + _qs(a, {}))
    if name == "search_entities":
        return _get("/entities" + _qs(a, {
            "name": a.get("name"), "type": a.get("type"),
            "limit": a.get("limit", 20),
        }))
    if name == "get_entity":
        return _get(f"/entities/{int(a['id'])}" + _qs(a, {}))
    if name == "get_neighbors":
        return _get(f"/entities/{int(a['id'])}/neighbors" + _qs(a, {}))
    if name == "get_provenance":
        return _get(f"/entities/{int(a['id'])}/provenance" + _qs(a, {}))
    if name == "ask":
        return _post("/ask", {
            "question": a["question"],
            "history": a.get("history") or [],
            "workspace_id": _ws(a),
        })
    if name == "cypher_read":
        q = str(a.get("query") or "")
        if _WRITE_RX.search(q):
            return {"error": "read-only — write keywords rejected"}
        return _post("/graph/cypher", {
            "query": q, "limit": int(a.get("limit", 50)),
            "workspace_id": _ws(a),
        })
    return {"error": f"unknown tool: {name}"}


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Single dispatch surface; convert REST errors into structured text."""
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
