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
from aryx.pipeline.enrich import _build_type_ancestors, _relate
from aryx.pipeline.fk_edges import link_by_attribute
from aryx.pipeline.stages import StageRunner
from aryx.store.checkpoint_store import StageTracker
from aryx.project import project_graph
from aryx.resolve_entities import resolve_run
from aryx.store.entity_store import EntityStore
from aryx.store.ontology_store import OntologyStore
from aryx.store.postgres_store import PostgresStore
from aryx.workspaces import ws_graph
from aryx.models import OntologyType

logger = logging.getLogger(__name__)

Progress = Callable[[str, int, str], None]


def _emit(cb: Progress | None, stage: str, pct: int, detail: str) -> None:
    """Report a pipeline stage to an optional progress callback."""
    if cb is not None:
        cb(stage, pct, detail)


def _register_types(dsn: str, workspace_id: int, estore: EntityStore) -> None:
    """Seed the ontology type registry from resolved entities.

    Ingest pins a type name onto every entity row (aryx_entity.ontology_type)
    but nothing registers that name as an ontology class, so the Model tab —
    which reads aryx_ontology_type — stays empty. Backfill the registry with
    every distinct type actually materialized in this workspace, deriving each
    type's attributes from the union of its entities' attribute keys.

    Best-effort: registry population is additive and must never block the
    projection that follows.
    """
    try:
        by_type: dict[str, set[str]] = {}
        for _id, etype, attrs in estore.list_entities():
            if not etype:
                continue
            by_type.setdefault(etype, set()).update((attrs or {}).keys())
        if not by_type:
            return
        ostore = OntologyStore(dsn, workspace_id)
        try:
            ostore.seed_types([
                OntologyType(name=name, attributes=sorted(keys),
                             status="approved", source="ingest")
                for name, keys in by_type.items()
            ])
        finally:
            ostore.close()
        logger.info("registered %d ontology type(s) ws=%s: %s",
                    len(by_type), workspace_id, sorted(by_type))
    except Exception as exc:  # noqa: BLE001 — never block projection on registry
        logger.warning("ontology type registration failed ws=%s: %s",
                       workspace_id, exc)


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
    resume_run_id: int | None = None,
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
        resume_run_id: Resume a crashed run — done stages skip, the landed
            data of that run is reused (no re-extract).

    Returns:
        Summary of {run_id, entities, relationships} plus graph projection counts.
    """
    if resume_run_id is not None:
        run_id = resume_run_id
        runner = StageRunner(dsn, run_id, resume=True)
        logger.info("resuming run_id=%s", run_id)
    else:
        _emit(on_progress, "Discover", 10, "Extracting, profiling and landing source records")
        store = PostgresStore(dsn, workspace_id)
        try:
            run_id = discover(connector, store, system, dataset,
                              broker=broker if tag else None)
        finally:
            store.close()
        runner = StageRunner(dsn, run_id, resume=False)
        tracker = StageTracker(dsn)
        tracker.start(run_id, "discover")
        tracker.finish(run_id, "discover")

    estore = EntityStore(dsn, workspace_id)
    entities = relationships = 0
    try:
        if not runner.skip("resolve_cluster"):
            _emit(on_progress, "Resolve", 50, "Resolving records into canonical entities")
            with runner.stage("resolve_cluster"):
                entities = resolve_run(run_id, ontology_type, match_keys,
                                       estore, broker)
        if relate and not runner.skip("relate"):
            _emit(on_progress, "Relate", 75, "Inferring relationships between entities")
            with runner.stage("relate"):
                relationships = _relate(estore, broker, max_pairs)
        if fk_links and not runner.skip("fk_link"):
            _emit(on_progress, "Link", 80, "Linking entities by foreign-key attributes")
            with runner.stage("fk_link"):
                for spec in fk_links:
                    relationships += link_by_attribute(
                        estore, spec["source_type"], spec["source_attr"],
                        spec["target_type"], spec["target_attr"], spec["name"],
                    )
        _register_types(dsn, workspace_id, estore)
        _emit(on_progress, "Project", 90, "Projecting entities and edges to the graph")
        with runner.stage("project"):
            type_ancestors = _build_type_ancestors(dsn)
            counts = project_graph(
                estore, FalkorStore(graph_url, ws_graph(workspace_id)),
                type_ancestors=type_ancestors, workspace_id=workspace_id,
            )
    finally:
        estore.close()

    summary = {"run_id": run_id, "entities": entities,
               "relationships": relationships, **counts}
    _emit(on_progress, "Done", 100, f"{entities} entities, {relationships} relationships")
    logger.info("pipeline complete %s", summary)
    return summary


def link_entities(
    dsn: str, graph_url: str, workspace_id: int, fk_links: list[dict],
) -> dict[str, int]:
    """Create FK edges across already-resolved entities, then re-project.

    A post-ingest pass for multi-source uploads: once every file's entities
    have landed, materialize the cross-file foreign-key edges (exact value
    matches only) and re-project the workspace graph so the edges appear.

    Args:
        dsn: Postgres DSN.
        graph_url: FalkorDB connection URL.
        workspace_id: Workspace to link and project.
        fk_links: FK specs — {source_type, source_attr, target_type,
            target_attr, name}.

    Returns:
        {relationships, ...projection counts}.
    """
    estore = EntityStore(dsn, workspace_id)
    relationships = 0
    try:
        for spec in fk_links:
            relationships += link_by_attribute(
                estore, spec["source_type"], spec["source_attr"],
                spec["target_type"], spec["target_attr"], spec["name"],
            )
        type_ancestors = _build_type_ancestors(dsn)
        counts = project_graph(
            estore, FalkorStore(graph_url, ws_graph(workspace_id)),
            type_ancestors=type_ancestors, workspace_id=workspace_id,
        )
    finally:
        estore.close()
    logger.info("link_entities workspace=%s relationships=%d", workspace_id, relationships)
    return {"relationships": relationships, **counts}
