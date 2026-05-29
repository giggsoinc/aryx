"""Aryx MCP server (Inc 11) — stdio transport, read-only, 4 tools.

Wraps the live Aryx REST API so Claude Desktop can query the knowledge graph.
Set ARYX_API_URL to point at the running API instance.

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "aryx": {
        "command": "python",
        "args": ["-m", "aryx.mcp"],
        "env": { "ARYX_API_URL": "http://ec2-3-91-73-197.compute-1.amazonaws.com:8088" }
      }
    }
  }
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("ARYX_API_URL", "http://localhost:8088").rstrip("/")

server = Server("aryx")


def _get(path: str) -> Any:
    url = f"{_API_URL}{path}"
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_entities",
            description=(
                "Search the Aryx knowledge graph for entities by name or type. "
                "Returns id, type, and name for each match."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name substring to search for."},
                    "type": {"type": "string", "description": "Ontology type filter, e.g. 'Customer'."},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        types.Tool(
            name="get_entity",
            description="Get full details for one entity by its numeric id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Entity id."},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="get_neighbors",
            description=(
                "Return one-hop relationships from an entity in both directions. "
                "Each result includes the related entity and the relationship name."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Entity id."},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="get_provenance",
            description=(
                "Return the source records an entity was resolved from — "
                "which system, dataset, and record it came from."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Entity id."},
                },
                "required": ["id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "search_entities":
            params: list[str] = []
            if arguments.get("name"):
                params.append(f"name={urllib.parse.quote(arguments['name'])}")
            if arguments.get("type"):
                params.append(f"type={urllib.parse.quote(arguments['type'])}")
            params.append(f"limit={arguments.get('limit', 20)}")
            result = _get(f"/entities?{'&'.join(params)}")

        elif name == "get_entity":
            result = _get(f"/entities/{int(arguments['id'])}")

        elif name == "get_neighbors":
            result = _get(f"/entities/{int(arguments['id'])}/neighbors")

        elif name == "get_provenance":
            result = _get(f"/entities/{int(arguments['id'])}/provenance")

        else:
            result = {"error": f"unknown tool: {name}"}

    except Exception as exc:
        result = {"error": str(exc)}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
