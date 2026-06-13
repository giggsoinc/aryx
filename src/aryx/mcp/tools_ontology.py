"""MCP tool specs for ontology read + export (Slice 4).

Two tools. ontology_get returns approved types + relationships.
ontology_export emits DDL/Cypher/RDF for the target the agent picks —
relational schemas for SQL warehouses, constraints for Neo4j, RDF for
semantic-web tooling. Oracle is intentionally a stub today.
"""
from __future__ import annotations

import mcp.types as types


def ontology_tool_specs() -> list[types.Tool]:
    """Return the 2 ontology tool specs."""
    return [
        types.Tool(
            name="ontology_get",
            description=(
                "Return the workspace's approved ontology: types (with "
                "attributes + instance counts) and relationships (with "
                "counts). The source of truth for the schema Aryx infers "
                "from your data."
            ),
            inputSchema={
                "type": "object",
                "properties": {"workspace_id": {"type": "integer"}},
                "required": ["workspace_id"],
            },
        ),
        types.Tool(
            name="ontology_export",
            description=(
                "Emit the ontology as deployable artefacts. target options: "
                "postgres / mysql / snowflake (table-per-type plus join "
                "tables per relationship); neo4j (uniqueness constraints "
                "per label); turtle / json-ld (RDF text via the existing "
                "RDF exporter); oracle (stub — returns a note, parked). "
                "Returns {target, format, statements|payload}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer"},
                    "target": {"type": "string",
                                "enum": ["postgres", "postgresql", "mysql",
                                          "snowflake", "neo4j", "turtle",
                                          "json-ld", "jsonld", "oracle"]},
                },
                "required": ["workspace_id", "target"],
            },
        ),
    ]
