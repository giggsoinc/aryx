"""FalkorDB writer for the knowledge-graph projection (stage 5d).

The graph is a rebuildable projection of the RDB (the source of truth), so the
writer always wipes and rebuilds. Entity nodes carry their ontology type;
provenance edges link entities to source records; REL edges connect entities.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from falkordb import FalkorDB

logger = logging.getLogger(__name__)


class FalkorStore:
    """Writes entity / provenance / relationship graph elements to FalkorDB."""

    def __init__(self, url: str, graph: str = "aryx") -> None:
        """Connect from a redis:// URL and select a named graph.

        Args:
            url: FalkorDB connection URL, e.g. redis://falkordb:6379.
            graph: Graph key to write into.
        """
        parsed = urlparse(url)
        self._db = FalkorDB(host=parsed.hostname or "localhost",
                            port=parsed.port or 6379)
        self._graph = self._db.select_graph(graph)

    def clear(self) -> None:
        """Delete the whole graph for a clean rebuild."""
        try:
            self._graph.delete()
        except Exception:  # graph may not exist yet  # noqa: BLE001
            pass

    def add_entity(self, entity_id: int, ontology_type: str,
                   attributes: dict[str, Any]) -> None:
        """Create or update an entity node labelled by its ontology type."""
        self._graph.query(
            "MERGE (e:Entity {id: $id}) SET e.type = $type, e.name = $name",
            {"id": entity_id, "type": ontology_type,
             "name": str(attributes.get("name") or attributes.get("full_name", ""))},
        )

    def add_provenance(self, entity_id: int, system: str, dataset: str,
                       record_id: str) -> None:
        """Link an entity to the source record it was discovered in."""
        self._graph.query(
            "MERGE (s:Source {system: $sys, dataset: $ds, record_id: $rid}) "
            "WITH s MATCH (e:Entity {id: $id}) MERGE (e)-[:FROM]->(s)",
            {"sys": system, "ds": dataset, "rid": record_id, "id": entity_id},
        )

    def add_relationship(self, source_id: int, target_id: int, name: str) -> None:
        """Create a typed edge between two entities."""
        self._graph.query(
            "MATCH (a:Entity {id: $src}), (b:Entity {id: $tgt}) "
            "MERGE (a)-[:REL {name: $name}]->(b)",
            {"src": source_id, "tgt": target_id, "name": name},
        )
