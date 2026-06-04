"""Aryx MCP server — stdio + SSE, read-only, 2 tools: list + ask.

Wraps the live Aryx REST API so any MCP-compatible agent (Claude Desktop,
Claude Code, Cursor, Continue) can discover workspaces and ask questions
against the knowledge graph. Set ARYX_API_URL to point at the API.
"""
from __future__ import annotations

import json
import logging
import os
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


def _ws(args: dict[str, Any]) -> int:
    """Resolve workspace_id from args or env default."""
    return int(args.get("workspace_id") or _DEFAULT_WS)


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


def _enrich_workspace(ws: dict) -> dict:
    """Add entity/relationship counts + type breakdown for one workspace."""
    wid = int(ws.get("id", 1))
    try:
        types_doc = _get(f"/ontology/types?workspace_id={wid}") or {}
    except Exception as exc:  # noqa: BLE001
        return {
            "id": wid, "name": ws.get("name", ""),
            "description": ws.get("description", ""),
            "brief": ws.get("brief", {}),
            "entity_count": 0, "relationship_count": 0,
            "entity_types": [], "relationship_types": [],
            "stats_error": str(exc),
        }

    def _norm(items: list, count_key: str) -> list[dict]:
        out: list[dict] = []
        for t in items or []:
            if isinstance(t, dict):
                out.append({
                    "name": t.get("name") or t.get("type") or "",
                    "count": int(t.get(count_key) or t.get("count") or 0),
                })
            else:
                out.append({"name": str(t), "count": 0})
        return [t for t in out if t["name"]]

    ents = _norm(types_doc.get("types") or types_doc.get("entity_types"),
                 "instance_count")
    rels = _norm(types_doc.get("relationships")
                 or types_doc.get("relationship_types"), "count")
    return {
        "id": wid,
        "name": ws.get("name", ""),
        "description": ws.get("description", ""),
        "brief": ws.get("brief", {}),
        "entity_count": int(types_doc.get("entity_count")
                            or sum(t["count"] for t in ents)),
        "relationship_count": sum(t["count"] for t in rels),
        "entity_types": ents,
        "relationship_types": rels,
    }


def _dispatch(name: str, a: dict) -> Any:
    """Route a tool call. Only `list` and `ask` are exposed."""
    if name == "list":
        workspaces = _get("/admin/workspaces?workspace_id=1") or []
        return [_enrich_workspace(ws) for ws in workspaces]
    if name == "ask":
        return _post("/ask", {
            "question": a["question"],
            "history": a.get("history") or [],
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
