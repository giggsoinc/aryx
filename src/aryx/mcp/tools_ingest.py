"""MCP tool specs for ingest: starting a run plus the HITL loop (Slice 3/5).

Five tools: ingest_file starts a run from raw file bytes; the other four
let agents poll pending questions, route them to the user, write answers
back, and peek at the projected entities/relationships before declaring
ingest done. ingest_status returns counts + job summary.
"""
from __future__ import annotations

from mcp import types


def ingest_tool_specs() -> list[types.Tool]:
    """Return the 5 ingest tool specs (1 start + 4 HITL)."""
    return [
        types.Tool(
            name="ingest_file",
            description=(
                "Start an ingest run from raw file bytes — up to 50 files, "
                "20MB each, 50MB total. Runs as a background job: returns "
                "job_id immediately, does NOT wait for completion. Use "
                "ingest_status(job_id=...) to poll, ingest_questions to "
                "resolve any clarifications the pipeline raises, and "
                "entities_preview once done. Dataset-shaped uploads (csv/"
                "json/xlsx) are content-addressed on disk, not stored in "
                "Postgres — the returned result never echoes raw bytes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "files": {
                        "type": "array",
                        "description": "Each item: {filename, content_base64}.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "content_base64": {"type": "string"},
                            },
                            "required": ["filename", "content_base64"],
                        },
                    },
                    "ontology_type": {"type": "string",
                                     "description": "Default 'Document'."},
                    "match_keys": {"type": "string",
                                  "description": "Comma-separated. Default 'name'."},
                    "fk_links": {"type": "array",
                                "description": "Optional foreign-key link plan."},
                    "graph_plan": {"type": "object",
                                  "description": "Optional pre-approved graph plan."},
                    "file_types": {
                        "type": "object",
                        "description": (
                            "Optional {filename: ontology_type} map — types "
                            "each file individually instead of forcing one "
                            "ontology_type on the whole batch. Required when "
                            "the files have different shapes (e.g. tickets.csv "
                            "+ customers.csv in one call) and you already know "
                            "each one's type; otherwise leave ontology_type "
                            "unset and each file is auto-typed from its own "
                            "columns."
                        ),
                    },
                },
                "required": ["workspace_id", "files"],
            },
        ),
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
