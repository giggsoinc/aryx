"""MCP tool definitions — 3 tools: list + ask + act.

`list` returns every workspace with its entity/relationship counts and type
breakdown — enough for an external agent to pick the right workspace_id
without making a second call. `ask` runs a natural-language question
against one workspace's graph.
"""
from __future__ import annotations

import mcp.types as types


def tool_specs() -> list[types.Tool]:
    """Return the tools the MCP server exposes (act is request-only)."""
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
        types.Tool(
            name="act",
            description=(
                "REQUEST an Aryx action on an entity. Agent-initiated "
                "mutations ALWAYS create a pending execution for human "
                "approval — they never auto-apply, regardless of the "
                "action's approval flag (DEC: trust posture). Returns the "
                "pending execution id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string",
                               "description": "Action name."},
                    "entity_id": {"type": "integer",
                                  "description": "Target entity id."},
                    "params": {"type": "object",
                               "description": "Action parameters."},
                    "workspace_id": {"type": "integer",
                                     "description": "From `list`."},
                },
                "required": ["action", "entity_id"],
            },
        ),
    ]
