"""Derive the Aryx graph JSON from stored entities and relationships (C05).

Turns the workspace's canonical entities/relationships into the graph JSON shape
the intake validator consumes: {"entities": [...], "relationships": [...]}.
"""
from __future__ import annotations

from typing import Any


def build_graph_json(
    entities: list[tuple[int, str, dict]],
    relationships: list[tuple[int, int, str]],
) -> dict[str, Any]:
    """Build a graph JSON payload from (id, type, attrs) + (src, tgt, name) rows.

    Entities and relationships are emitted in a canonical, deterministic order
    (entities by id; relationships by source/type/target) so the same data
    always produces the same JSON — and therefore the same content hash —
    regardless of the order the database returned the rows in.
    """
    ents = sorted(
        ({"id": str(eid), "type": etype or "Entity", "properties": attrs or {}}
         for eid, etype, attrs in entities),
        key=lambda e: e["id"],
    )
    rels = sorted(
        ({"source": str(src), "type": name, "target": str(tgt)}
         for src, tgt, name in relationships),
        key=lambda r: (r["source"], r["type"], r["target"]),
    )
    return {"entities": ents, "relationships": rels}
