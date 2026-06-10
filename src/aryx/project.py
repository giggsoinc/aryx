"""Knowledge-graph projection orchestration (stage 5d): RDB -> FalkorDB."""
from __future__ import annotations

import logging

from aryx.graph import FalkorStore
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def _entity_iri(base_uri: str, workspace_id: int | None, entity_id: int) -> str:
    """Mint the stable IRI for an entity.

    Deterministic from ``(workspace_id, entity_id)``; ``entity_id`` is a
    BIGSERIAL that is never reused, so the IRI is frozen for life.
    """
    base = base_uri if base_uri.endswith("/") else base_uri + "/"
    ws = workspace_id if workspace_id is not None else 0
    return f"{base}entity/{ws}/{entity_id}"


def project_graph(
    store: EntityStore,
    graph: FalkorStore,
    type_ancestors: dict[str, list[str]] | None = None,
    workspace_id: int | None = None,
    base_uri: str = "https://aryx.local/",
) -> dict[str, int]:
    """Rebuild the FalkorDB graph from the RDB (the source of truth).

    Wipes the graph, then writes entity nodes (with ancestor labels and a
    stable IRI when available), provenance edges, and relationship edges.
    Always safe to re-run.

    Args:
        store: Open entity store (reads from Postgres).
        graph: Open FalkorDB writer.
        type_ancestors: Optional ``{type_name: [parent, grandparent, ...]}``
            map. When supplied, ancestors are attached as additional Cypher
            labels (rdfs:subClassOf at the graph layer). When None, behavior
            matches the pre-hierarchy projection.
        workspace_id: Workspace this projection belongs to; folded into the
            entity IRI when present.
        base_uri: URI prefix for minted entity IRIs. Defaults to the local
            placeholder used in tests and ``ontology/rdf`` export.

    Returns:
        Counts of {entities, provenance, relationships} written.
    """
    graph.clear()
    entities = store.list_entities()
    ancestors_for = type_ancestors or {}
    for entity_id, ontology_type, attributes in entities:
        labels = ancestors_for.get(ontology_type, [])
        iri = _entity_iri(base_uri, workspace_id, entity_id)
        graph.add_entity(entity_id, ontology_type, attributes,
                         labels=labels, iri=iri)

    provenance = store.list_members_provenance()
    for entity_id, system, dataset, record_id in provenance:
        graph.add_provenance(entity_id, system, dataset, record_id)

    relationships = store.list_relationships()
    for source_id, target_id, name in relationships:
        graph.add_relationship(source_id, target_id, name)

    counts = {"entities": len(entities), "provenance": len(provenance),
              "relationships": len(relationships)}
    logger.info("graph projected %s labels_used=%d",
                counts, sum(1 for v in ancestors_for.values() if v))
    return counts
