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


def project_incremental(
    store: "EntityStore",
    pstore,
    graph: "FalkorStore",
    type_ancestors: dict[str, list[str]] | None = None,
    workspace_id: int | None = None,
    base_uri: str = "https://aryx.local/",
) -> dict[str, int]:
    """Update the graph in place from the Postgres dirty set (G8).

    Never calls ``clear()`` — the graph stays queryable throughout. Upserts
    dirty entities (MERGE is idempotent), re-MERGEs their provenance and
    relationship edges, DETACH-DELETEs tombstones, advances the watermark.
    ``pstore`` is a ProjectionStore; other args match ``project_graph``.

    Returns:
        Counts of {entities, provenance, relationships, tombstones} written.
    """
    since = pstore.watermark()
    ancestors_for = type_ancestors or {}
    dirty = pstore.dirty_entities(since)
    for entity_id, ontology_type, attributes in dirty:
        labels = ancestors_for.get(ontology_type, [])
        iri = _entity_iri(base_uri, workspace_id, entity_id)
        graph.add_entity(entity_id, ontology_type, attributes,
                         labels=labels, iri=iri)
    dirty_ids = [e[0] for e in dirty]
    provenance = pstore.provenance_for(dirty_ids) if dirty_ids else []
    for entity_id, system, dataset, record_id in provenance:
        graph.add_provenance(entity_id, system, dataset, record_id)
    relationships = pstore.relationships_for(dirty_ids) if dirty_ids else []
    for source_id, target_id, name in relationships:
        graph.add_relationship(source_id, target_id, name)
    tombstones = pstore.tombstones()
    for entity_id in tombstones:
        graph.remove_entity(entity_id)
    pstore.mark_projected(dirty_ids)
    pstore.unmark_projected(tombstones)
    pstore.advance_watermark()
    counts = {"entities": len(dirty), "provenance": len(provenance),
              "relationships": len(relationships),
              "tombstones": len(tombstones)}
    logger.info("graph incrementally projected %s", counts)
    return counts


def project_auto(
    store: "EntityStore",
    pstore,
    graph: "FalkorStore",
    dirty_ratio_max: float = 0.30,
    **kwargs,
) -> dict[str, int]:
    """Pick incremental vs full rebuild (G8 mode=auto).

    Incremental when a watermark exists AND the dirty set is under
    ``dirty_ratio_max`` (env ARYX_PROJECT_DIRTY_MAX overrides) of all
    entities; full rebuild otherwise — it remains the correctness anchor.
    """
    import os
    try:
        dirty_ratio_max = float(os.environ.get("ARYX_PROJECT_DIRTY_MAX",
                                               dirty_ratio_max))
    except ValueError:
        pass
    since = pstore.watermark()
    if since is not None:
        total = pstore.total_entities()
        dirty = len(pstore.dirty_entities(since))
        if total and dirty / total < dirty_ratio_max:
            return project_incremental(store, pstore, graph, **kwargs)
    counts = project_graph(store, graph, **kwargs)
    pstore.mark_projected([e[0] for e in store.list_entities()])
    pstore.advance_watermark()
    return counts
