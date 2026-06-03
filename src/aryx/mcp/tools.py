"""MCP tool definitions — split out of server.py to keep both under 150 lines.

8 read-only tools that wrap the Aryx REST API. Each tool accepts an optional
workspace_id so an external agent can switch contexts; without it the tool
defaults to workspace 1.
"""
from __future__ import annotations

import mcp.types as types

_WS = {
    "workspace_id": {
        "type": "integer", "default": 1,
        "description": "Workspace id (call list_workspaces to discover).",
    }
}


def tool_specs() -> list[types.Tool]:
    """Return the 8 read-only tools the MCP server exposes."""
    return [
        types.Tool(
            name="list_workspaces",
            description="Discover available Aryx workspaces (id + name).",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_types",
            description="List entity types + relationship types + counts.",
            inputSchema={"type": "object", "properties": dict(_WS)},
        ),
        types.Tool(
            name="search_entities",
            description=("Search by name or type. Returns id, type, name."),
            inputSchema={"type": "object", "properties": {
                "name": {"type": "string", "description": "Name substring."},
                "type": {"type": "string",
                         "description": "Ontology type filter, e.g. 'Customer'."},
                "limit": {"type": "integer", "default": 20},
                **_WS,
            }},
        ),
        types.Tool(
            name="get_entity",
            description="Full details for one entity by numeric id.",
            inputSchema={"type": "object", "properties": {
                "id": {"type": "integer"}, **_WS}, "required": ["id"]},
        ),
        types.Tool(
            name="get_neighbors",
            description=("One-hop relationships in both directions; each "
                         "result includes the related entity + rel name."),
            inputSchema={"type": "object", "properties": {
                "id": {"type": "integer"}, **_WS}, "required": ["id"]},
        ),
        types.Tool(
            name="get_provenance",
            description=("Source records an entity was resolved from — "
                         "which system, dataset, record."),
            inputSchema={"type": "object", "properties": {
                "id": {"type": "integer"}, **_WS}, "required": ["id"]},
        ),
        types.Tool(
            name="ask",
            description=("Ask a natural-language question over the workspace "
                         "graph; returns synthesised answer + entity ids."),
            inputSchema={"type": "object", "properties": {
                "question": {"type": "string"},
                "history": {"type": "array", "default": []},
                **_WS,
            }, "required": ["question"]},
        ),
        types.Tool(
            name="cypher_read",
            description=("Run a read-only Cypher MATCH query against the "
                         "workspace graph. Rejects writes (CREATE/MERGE/"
                         "DELETE/SET/REMOVE/DROP)."),
            inputSchema={"type": "object", "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                **_WS,
            }, "required": ["query"]},
        ),
    ]
