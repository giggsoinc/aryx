"""MCP tool definitions — 2 tools only: list + ask.

`list` returns every workspace with its entity/relationship counts and type
breakdown — enough for an external agent to pick the right workspace_id
without making a second call. `ask` runs a natural-language question
against one workspace's graph.
"""
from __future__ import annotations

import mcp.types as types


def tool_specs() -> list[types.Tool]:
    """Return the 2 read-only tools the MCP server exposes."""
    return [
        types.Tool(
            name="list",
            description=(
                "List every Aryx workspace with its contents — id, name, "
                "description, brief, entity count, relationship count, and "
                "the entity/relationship types present (with counts). Call "
                "this first to discover which workspace_id to pass to `ask`."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="ask",
            description=(
                "Ask a natural-language question over a workspace's knowledge "
                "graph. Returns a synthesised answer plus the entity ids the "
                "answer is grounded in. Pass workspace_id from `list` — if "
                "omitted, the server's default workspace is used."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural-language question.",
                    },
                    "workspace_id": {
                        "type": "integer",
                        "description": (
                            "Workspace id from `list`. Optional — falls back "
                            "to ARYX_MCP_DEFAULT_WORKSPACE on the server."
                        ),
                    },
                },
                "required": ["question"],
            },
        ),
    ]
