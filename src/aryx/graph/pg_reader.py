"""Postgres graph reader — serves the knowledge graph straight from the RDB.

Replaces the FalkorDB projection. Entities, edges and provenance already live
in the ``aryx_*`` tables, partitioned by workspace, so every read here is one
indexed query scoped by ``workspace_id`` — there is no second copy to keep in
sync. Behaviour is held identical to the old reader by the golden file in
``tests/fixtures/graph_golden``: duplicate edges collapse, edges to missing
entities are ignored, and a node's display name comes from
``aryx_display_name`` (a port of the old ``_display_name``).
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.graph.pg_path import GraphSearchTooLarge, directed_path
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

# Re-exported: callers import the exception from here.
__all__ = ["GraphSearchTooLarge", "PostgresGraphReader"]

_MAX_LIMIT = 500
_MAX_HOPS = 10

_FIND_QUERIES = {
    (False, False): "graph_find_entities_all",
    (True, False): "graph_find_entities_by_type",
    (False, True): "graph_find_entities_by_name",
    (True, True): "graph_find_entities_by_type_and_name",
}


class PostgresGraphReader:
    """Reads entities, relationships and provenance for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Borrow the shared pool for ``dsn`` and bind to one workspace.

        Args:
            dsn: Postgres connection string.
            workspace_id: Workspace whose partition every query is scoped to.
        """
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def _rows(self, query: str, params: dict[str, Any]) -> list[tuple]:
        """Run a named query with the workspace bound; return every row."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load(query), {"ws": self._ws, **params})
                return cur.fetchall()

    def get_entity(self, entity_id: int) -> dict[str, Any] | None:
        """Return a single entity's id/type/name, or None if absent."""
        rows = self._rows("graph_get_entity", {"id": int(entity_id)})
        if not rows:
            return None
        return self._attach_labels([_entity(rows[0])])[0]

    def find_entities(self, ontology_type: str | None = None,
                      name: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Find entities by exact type and/or case-insensitive name substring.

        Args:
            ontology_type: Exact ontology type, or None for any.
            name: Substring matched case-insensitively against the display
                name, or None. Percent, underscore and backslash are literal.
            limit: Maximum rows (clamped to 1..500).

        Returns:
            ``{id, type, name}`` dicts ordered by id.
        """
        params: dict[str, Any] = {"limit": max(1, min(int(limit), _MAX_LIMIT))}
        if ontology_type:
            params["type"] = ontology_type
        if name:
            params["name"] = name
        query = _FIND_QUERIES[(bool(ontology_type), bool(name))]
        return self._attach_labels([_entity(r) for r in self._rows(query, params)])

    def neighbors(self, entity_id: int) -> list[dict[str, Any]]:
        """Return one-hop related entities in both directions.

        Each result carries the edge name and its direction ('out' or 'in')
        relative to the queried entity, plus the connected entity's fields.
        Edges made by the reasoning engine also carry ``inferred: True``.
        """
        rows = self._rows("graph_neighbors", {"id": int(entity_id)})
        items = []
        for r in rows:
            item = {**_entity(r), "relationship": r[3], "direction": r[4]}
            if r[5]:
                item["inferred"] = True
            items.append(item)
        return self._attach_labels(items)

    def all_relationships(self) -> list[dict[str, Any]]:
        """Return every distinct relationship edge in the workspace.

        Edges made by the reasoning engine also carry ``inferred: True``.
        """
        out = []
        for r in self._rows("graph_all_relationships", {}):
            edge = {"source": r[0], "target": r[1], "name": r[2]}
            if r[3]:
                edge["inferred"] = True
            out.append(edge)
        return out

    def provenance(self, entity_id: int) -> list[dict[str, Any]]:
        """Return the source records an entity was resolved from."""
        rows = self._rows("graph_provenance", {"id": int(entity_id)})
        return [{"system": r[0], "dataset": r[1], "record_id": r[2]}
                for r in rows]

    def count_by_relationship(self, source_type: str, relationship: str,
                              target_type: str, direction: str = "out") -> dict[str, int]:
        """Count source_type entities grouped by the target_type entity name
        they relate to through one named relationship (one hop).

        Args:
            source_type: Ontology type of the entities being counted.
            relationship: The edge's name.
            target_type: Ontology type of the entity each count is grouped by.
            direction: 'out' for (source)-[rel]->(target), 'in' to reverse it.

        Returns:
            ``{target_entity_name: count}``; empty when nothing matches.
        """
        query = ("graph_count_by_relationship_in" if direction == "in"
                 else "graph_count_by_relationship_out")
        rows = self._rows(query, {"rel": relationship, "source_type": source_type,
                                  "target_type": target_type})
        return {str(r[0]): int(r[1]) for r in rows}

    def shortest_path(self, src: int, dst: int, max_hops: int = 6) -> list[dict[str, Any]]:
        """Return the shortest path between two entities, or [].

        Mirrors the old reader exactly: one search along edge direction
        (src to dst) and one against it (dst to src, never mixed), keep the
        shorter, outbound wins a tie. An inbound result is therefore listed in
        edge direction, destination first. A node never has a path to itself.
        """
        src, dst = int(src), int(dst)
        hops = max(1, min(int(max_hops), _MAX_HOPS))
        if src == dst or len(self._labels([src, dst])) < 2:
            return []
        found = [p for p in (directed_path(self._rows, src, dst, hops),
                             directed_path(self._rows, dst, src, hops)) if p]
        if not found:
            return []
        chain = min(found, key=len)  # min() keeps the first (outbound) on a tie
        labels = self._labels([node for node, _ in chain])
        return [{"id": node, "type": labels[node][0], "name": labels[node][1],
                 "relationship": rel} for node, rel in chain]

    def _attach_labels(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add ``inferred_label`` to entities the reasoning engine labelled."""
        if not items:
            return items
        rows = self._rows("graph_inferred_labels", {"ids": [i["id"] for i in items]})
        labels = {int(r[0]): r[1] for r in rows}
        for item in items:
            if item["id"] in labels:
                item["inferred_label"] = labels[item["id"]]
        return items

    def _labels(self, ids: list[int]) -> dict[int, tuple[str, str]]:
        """Map entity id -> (type, display name) for the ids that exist."""
        rows = self._rows("graph_labels_by_ids", {"ids": ids})
        return {int(r[0]): (r[1], r[2]) for r in rows}


def _entity(row: tuple) -> dict[str, Any]:
    """Map an (id, type, name) result row to an entity dict."""
    return {"id": int(row[0]), "type": row[1], "name": row[2]}
