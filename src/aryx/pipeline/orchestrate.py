"""End-to-end pipeline orchestration (Increment 7): source -> graph.

Chains the existing stages into one runnable flow: discover (extract/clean/
profile/land, + cheap-tier tag when enabled) -> resolve landed records into
canonical entities -> optional frontier relationship inference -> project to
FalkorDB. The LLM stages (tag, relate) are opt-in, so the deterministic spine
runs end-to-end without any model configured.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from aryx.broker import Broker
from aryx.connectors.base import Connector
from aryx.discover import discover
from aryx.graph import FalkorStore
from aryx.models import Relationship
from aryx.pipeline.fk_edges import link_by_attribute
from aryx.project import project_graph
from aryx.relationships import infer_relationship
from aryx.resolve_entities import resolve_run
from aryx.store.entity_store import EntityStore
from aryx.store.postgres_store import PostgresStore
from aryx.workspaces import ws_graph

logger = logging.getLogger(__name__)

Progress = Callable[[str, int, str], None]


def _emit(cb: Progress | None, stage: str, pct: int, detail: str) -> None:
    """Report a pipeline stage to an optional progress callback."""
    if cb is not None:
        cb(stage, pct, detail)


def _relate(store: EntityStore, broker: Broker, max_pairs: int) -> int:
    """Infer relationships over candidate entity pairs (frontier tier).

    A naive all-pairs candidate strategy capped at max_pairs; deterministic
    FK/co-occurrence pair selection is a later increment.
    """
    entities = store.list_entities()
    rels: list[Relationship] = []
    pairs = 0
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            if pairs >= max_pairs:
                break
            left, right = entities[i], entities[j]
            name, conf = infer_relationship(left[2], right[2], broker)
            if name:
                rels.append(Relationship(
                    source_entity_id=left[0], target_entity_id=right[0],
                    name=name, confidence=conf))
            pairs += 1
    store.save_relationships(rels)
    return len(rels)


def run_pipeline(
    connector: Connector,
    dsn: str,
    system: str,
    dataset: str,
    ontology_type: str,
    match_keys: list[str],
    graph_url: str,
    broker: Broker,
    tag: bool = False,
    relate: bool = False,
    max_pairs: int = 50,
    on_progress: Progress | None = None,
    fk_links: list[dict] | None = None,
    workspace_id: int = 1,
) -> dict[str, int]:
    """Run a source from extraction through to the FalkorDB projection.

    Args:
        connector: Configured source connector.
        dsn: Postgres DSN (the source of truth).
        system: Source system label.
        dataset: Source dataset/table label.
        ontology_type: Canonical type the records resolve into (pinned).
        match_keys: Payload keys whose values form the resolution match text.
        graph_url: FalkorDB connection URL.
        broker: Model broker (required by resolution; LLM only on opt-in stages).
        tag: Run cheap-tier field tagging during discovery.
        relate: Infer relationships between resolved entities (frontier tier).
        max_pairs: Cap on candidate pairs when relate is enabled.

    Returns:
        Summary of {run_id, entities, relationships} plus graph projection counts.
    """
    _emit(on_progress, "Discover", 10, "Extracting, profiling and landing source records")
    store = PostgresStore(dsn, workspace_id)
    try:
        run_id = discover(connector, store, system, dataset,
                          broker=broker if tag else None)
    finally:
        store.close()

    estore = EntityStore(dsn, workspace_id)
    try:
        _emit(on_progress, "Resolve", 50, "Resolving records into canonical entities")
        entities = resolve_run(run_id, ontology_type, match_keys, estore, broker)
        if relate:
            _emit(on_progress, "Relate", 75, "Inferring relationships between entities")
        relationships = _relate(estore, broker, max_pairs) if relate else 0
        if fk_links:
            _emit(on_progress, "Link", 80, "Linking entities by foreign-key attributes")
            for spec in fk_links:
                relationships += link_by_attribute(
                    estore, spec["source_type"], spec["source_attr"],
                    spec["target_type"], spec["target_attr"], spec["name"],
                )
        _emit(on_progress, "Project", 90, "Projecting entities and edges to the graph")
        counts = project_graph(estore, FalkorStore(graph_url, ws_graph(workspace_id)))
    finally:
        estore.close()

    summary = {"run_id": run_id, "entities": entities,
               "relationships": relationships, **counts}
    _emit(on_progress, "Done", 100, f"{entities} entities, {relationships} relationships")
    logger.info("pipeline complete %s", summary)
    return summary
