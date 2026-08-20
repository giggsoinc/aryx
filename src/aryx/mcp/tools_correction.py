"""MCP tool specs for graph correction (Slice 6).

Two tools, mirroring the UI's own propose-then-apply chat flow rather
than a single direct-apply call: agent-initiated graph mutations should
face a confirmation step, matching the trust posture already established
for `act` (aryx.mcp.act) — an agent proposes, the human (or an explicit
follow-up call after the human agrees) applies.
"""
from __future__ import annotations

from mcp import types

_KINDS = ["retype", "remove", "link", "unlink", "merge", "rename_type"]


def correction_tool_specs() -> list[types.Tool]:
    """Return the 2 correction tool specs."""
    return [
        types.Tool(
            name="correction_propose",
            description=(
                "Parse a plain-language correction ('Maria is a HumanRole', "
                "'merge X into Y') into a structured proposal. Does NOT "
                "apply anything — returns {status, message, action}. Show "
                "the message to the user; only call correction_apply with "
                "the returned `action` once they confirm."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "text": {"type": "string",
                             "description": "The correction utterance."},
                    "selected_entity_id": {
                        "type": "integer",
                        "description": "Entity the user has selected, if any "
                                       "— resolves 'this'/'it'.",
                    },
                },
                "required": ["workspace_id", "text"],
            },
        ),
        types.Tool(
            name="correction_apply",
            description=(
                "Apply a correction. MUTATES the knowledge graph and "
                "re-projects it immediately — there is no further "
                "confirmation step after this call. Pass exactly the "
                "`action` object correction_propose returned, or build one "
                "directly if you already know the exact kind/entity_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "kind": {"type": "string", "enum": _KINDS},
                    "entity_id": {"type": "integer"},
                    "target_id": {"type": "integer",
                                 "description": "merge/link/unlink target."},
                    "name": {"type": "string",
                            "description": "New type (retype) or "
                                          "relationship name (link)."},
                    "type_name": {"type": "string",
                                 "description": "rename_type: the existing "
                                               "type name to rename."},
                },
                "required": ["workspace_id", "kind"],
            },
        ),
    ]
