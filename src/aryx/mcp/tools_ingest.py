"""MCP tool specs for HITL ingest (Slice 3).

Four tools: agents poll pending questions, route them to the user, write
answers back, and peek at the projected entities/relationships before
declaring ingest done. ingest_status returns counts + job summary.
"""
from __future__ import annotations

import mcp.types as types


def ingest_tool_specs() -> list[types.Tool]:
    """Return the 4 HITL ingest tool specs."""
    return [
        types.Tool(
            name="ingest_questions",
            description=(
                "List clarifying questions the pipeline has raised. Each "
                "row carries kind, prompt, options (optional), suggested "
                "answer, and status. Default returns pending only. Use "
                "ingest_answer to resolve a row and unblock the pipeline."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "status": {"type": "string",
                                "description": "pending|answered|'' for all"},
                    "limit": {"type": "integer"},
                },
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="ingest_answer",
            description=(
                "Resolve a pending question. answered_by defaults to "
                "mcp-agent — set it to the user's name when the agent is "
                "relaying the user's reply for a clean audit trail."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer"},
                    "answer": {"type": "string"},
                    "answered_by": {"type": "string"},
                },
                "required": ["question_id", "answer"],
            },
        ),
        types.Tool(
            name="ingest_status",
            description=(
                "Snapshot of an ingest run: question counts by status plus "
                "the job's stage/progress if job_id is provided. Use this "
                "to decide whether to wait, ask more questions, or finish."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "job_id": {"type": "string"},
                },
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="entities_preview",
            description=(
                "Return up to `limit` entities and ~3× edges from the live "
                "graph projection. Use to confirm visually with the user "
                "before declaring ingest complete — 'this is what Aryx "
                "now knows about your domain.'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["workspace_id"],
            },
        ),
    ]
