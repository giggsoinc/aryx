"""MCP tool specs for datasource registry (Slice 2).

Five tools. The flow an agent runs: datasource_quiz(kind) → ask the user
each field → datasource_add(...) → datasource_test(id) → if ok, proceed
to ingest. Secrets are Fernet-encrypted at the API boundary; responses
return only a non-reversible mask.
"""
from __future__ import annotations

import mcp.types as types


def datasource_tool_specs() -> list[types.Tool]:
    """Return the 5 datasource tool specs."""
    return [
        types.Tool(
            name="datasource_quiz",
            description=(
                "Return the question pack for a datasource kind — the list "
                "of fields the agent must ask the user, each annotated with "
                "name, required, secret, help. Call with no kind to discover "
                "supported kinds and confirm the server's secret key is set."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kind": {"type": "string",
                              "description": "postgresql / mysql / oracle / "
                                              "docs / rest (optional)."},
                },
            },
        ),
        types.Tool(
            name="datasource_add",
            description=(
                "Register a datasource. The 'secret' field is Fernet-"
                "encrypted on receipt and never returned. Response carries "
                "secret_mask only (••••<hash4>). Use datasource_test next to "
                "confirm the credentials work."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "name": {"type": "string",
                              "description": "Friendly name for the source."},
                    "kind": {"type": "string"},
                    "config": {"type": "object",
                                "description": "Non-secret fields: host, "
                                                "port, database, user, etc."},
                    "secret": {"type": "string",
                                "description": "Plaintext password / token "
                                                "(encrypted before storage)."},
                },
                "required": ["workspace_id", "name", "kind"],
            },
        ),
        types.Tool(
            name="datasource_list",
            description=(
                "List datasources in a workspace. Never returns plaintext or "
                "ciphertext — only the mask. Use the returned id with "
                "datasource_test or downstream ingest tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {"workspace_id": {"type": "integer"}},
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="datasource_test",
            description=(
                "Open the datasource with its decrypted secret and probe it: "
                "SQL → SELECT 1 + list 25 tables; docs → list 25 files; "
                "rest → reachability deferred. Audit log records the "
                "decrypt. Returns {ok, tables?|files?|error}."
            ),
            inputSchema={
                "type": "object",
                "properties": {"datasource_id": {"type": "integer"}},
                "required": ["datasource_id"],
            },
        ),
        types.Tool(
            name="datasource_delete",
            description=(
                "Hard-delete a datasource. Cascades the audit trail. No undo."
            ),
            inputSchema={
                "type": "object",
                "properties": {"datasource_id": {"type": "integer"}},
                "required": ["datasource_id"],
            },
        ),
    ]
