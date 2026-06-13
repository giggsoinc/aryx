"""MCP tool definitions — read, act, and onboarding (Slice 1).

Read: ``list``, ``ask``. Act: ``act`` (G13). Onboarding: workspace_list /
workspace_create / workspace_select / brief_get / brief_draft / brief_set /
brief_save — together these let an agent drive the setup quiz with the user.
"""
from __future__ import annotations

import mcp.types as types

from aryx.mcp.tools_datasource import datasource_tool_specs
from aryx.mcp.tools_onboard import onboard_tool_specs


def tool_specs() -> list[types.Tool]:
    """Return every MCP tool: read + act + onboarding + datasource."""
    return (_read_act_specs() + onboard_tool_specs()
            + datasource_tool_specs())


def _read_act_specs() -> list[types.Tool]:
    """The original read/act tools — list, ask, act."""
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
