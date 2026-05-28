"""Knowledge-graph projection orchestration (stage 5d): RDB -> FalkorDB."""
from __future__ import annotations

import logging

from aryx.graph import FalkorStore
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def project_graph(store: EntityStore, graph: FalkorStore) -> dict[str, int]:
    """Rebuild the FalkorDB graph from the RDB (the source of truth).

    Wipes the graph, then writes entity nodes, provenance edges to source
    records, and relationship edges. Always safe to re-run.

    Args:
        store: Open entity store (reads from Postgres).
        graph: Open FalkorDB writer.

    Returns:
        Counts of {entities, provenance, relationships} written.
    """
    graph.clear()
    entities = store.list_entities()
    for entity_id, ontology_type, attributes in entities:
        graph.add_entity(entity_id, ontology_type, attributes)

    provenance = store.list_members_provenance()
    for entity_id, system, dataset, record_id in provenance:
        graph.add_provenance(entity_id, system, dataset, record_id)

    relationships = store.list_relationships()
    for source_id, target_id, name in relationships:
        graph.add_relationship(source_id, target_id, name)

    counts = {"entities": len(entities), "provenance": len(provenance),
              "relationships": len(relationships)}
    logger.info("graph projected %s", counts)
    return counts
