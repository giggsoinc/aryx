"""MCP tool specs for the onboarding flow (Slice 1).

Seven tools: 3 workspace + 4 brief. Each spec is small but the prose is
deliberately rich so an external agent (Claude Desktop, Cursor, an LLM
loop) understands the quiz protocol without docs: call ``brief_get``,
read ``next_question``, ask the user, call ``brief_set``, loop.
"""
from __future__ import annotations

import mcp.types as types


def onboard_tool_specs() -> list[types.Tool]:
    """Return the 7 onboarding tool specs."""
    return [
        types.Tool(
            name="workspace_list",
            description=(
                "List every Aryx workspace with id, name, description, "
                "brief, and timestamps. Call before workspace_create to "
                "avoid duplicates."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="workspace_create",
            description=(
                "Create a new isolated workspace. Each workspace owns its "
                "own LIST partitions in Postgres and a named graph in "
                "FalkorDB — total tenant isolation. Returns {id, name}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "context": {"type": "string",
                                 "description": "Optional free-text "
                                 "business context."},
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="workspace_select",
            description=(
                "Confirm a workspace exists and return its row. Use as the "
                "agent's 'now we are in this workspace' acknowledgement "
                "before any brief_* or ingest call."
            ),
            inputSchema={
                "type": "object",
                "properties": {"workspace_id": {"type": "integer"}},
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="brief_get",
            description=(
                "Return the workspace's current brief, its readiness depth "
                "(Generic NER → Grounded → Sharp → Expert), and "
                "next_question — the prompt for the FIRST EMPTY field. "
                "next_question = null means the brief is complete; "
                "otherwise show next_question to the user and pass their "
                "reply to brief_set."
            ),
            inputSchema={
                "type": "object",
                "properties": {"workspace_id": {"type": "integer"}},
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="brief_draft",
            description=(
                "AI-draft the entire 5-field brief from a seed sentence "
                "and/or document text the user supplies. Use this when the "
                "user uploads a deck / SOW / PDF or gives one-line intent. "
                "The user then edits a strong draft instead of authoring "
                "from a blank form."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "seed": {"type": "string",
                              "description": "One-sentence intent."},
                    "doc_text": {"type": "string",
                                  "description": "Optional document text."},
                },
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="brief_set",
            description=(
                "Patch ONE field of the brief. field ∈ {domain, aim, "
                "objectives, scope, roles}. value is a string; for "
                "objectives and roles, newline-separated lines become list "
                "items. Returns the updated brief + next_question + depth."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "field": {"type": "string",
                               "enum": ["domain", "aim", "objectives",
                                        "scope", "roles"]},
                    "value": {"type": "string"},
                },
                "required": ["workspace_id", "field", "value"],
            },
        ),
        types.Tool(
            name="brief_save",
            description=(
                "Persist the brief atomically. Optional 'brief' overrides "
                "the saved one (whole-object save). Returns depth + "
                "next_question. Brief grounds every extraction prompt."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "brief": {"type": "object"},
                },
                "required": ["workspace_id"],
            },
        ),
    ]
