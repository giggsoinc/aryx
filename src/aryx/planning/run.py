"""Glue: gather a dataset's artifacts and assemble its planning context (C07).

Shared by the ingest auto-trigger, backfill, and API. Loads the C03 profile,
C04 semantic profile, C06 graph profile, and C01 intent (via the dataset's
request_id), then assembles and persists the planning context.
"""
from __future__ import annotations

import logging

from aryx.planning.assemble import assemble_context, assemble_workspace_context
from aryx.planning.catalogues import CHARTS, OPERATIONS
from aryx.planning.models import PlanningContext
from aryx.store.context_store import ContextStore
from aryx.store.dataset_store import DatasetStore
from aryx.store.graph_profile_store import GraphProfileStore
from aryx.store.profile_store import ProfileStore
from aryx.store.semantic_store import SemanticStore

logger = logging.getLogger(__name__)


def run_context(dsn: str, workspace_id: int, dataset_id: str,
                version: str | None = None) -> PlanningContext | None:
    """Assemble and persist the planning context for a dataset version."""
    pstore = ProfileStore(dsn, workspace_id)
    try:
        profile = pstore.get(dataset_id, version) if version else pstore.latest(dataset_id)
    finally:
        pstore.close()
    if profile is None:
        return None
    ver = profile.dataset_version

    sstore = SemanticStore(dsn, workspace_id)
    try:
        semantic = sstore.get(dataset_id, ver) or sstore.latest(dataset_id)
    finally:
        sstore.close()

    gstore = GraphProfileStore(dsn, workspace_id)
    try:
        graph_profile = gstore.latest(f"graph_workspace_{workspace_id}")
    finally:
        gstore.close()

    intent = None
    dstore = DatasetStore(dsn, workspace_id)
    try:
        latest_ds = dstore.latest(dataset_id)
    finally:
        dstore.close()
    if latest_ds and latest_ds.request_id:
        from aryx.store.intent_store import IntentStore
        istore = IntentStore(dsn, workspace_id)
        try:
            intent = istore.get(latest_ds.request_id)
        finally:
            istore.close()

    ctx = assemble_context(
        dataset_id=dataset_id, dataset_version=ver,
        dataset_profile=profile, semantic_profile=semantic,
        graph_profile=graph_profile, intent=intent,
        operations=OPERATIONS, charts=CHARTS,
    )
    store = ContextStore(dsn, workspace_id)
    try:
        store.save(ctx)
    finally:
        store.close()
    logger.info("planning context ws=%s dataset=%s status=%s cols=%d paths=%d",
                workspace_id, dataset_id, ctx.context_status,
                len(ctx.approved_columns), len(ctx.approved_graph_paths))
    return ctx


def run_workspace_context(dsn: str, workspace_id: int) -> PlanningContext | None:
    """Assemble and persist ONE merged planning context spanning every dataset
    profiled in this workspace. Free/deterministic (no LLM) — safe to auto-run
    on every ingest, unlike C08. Re-running replaces the single living row
    (there is no immutable-snapshot need here, unlike C05's graph versions)."""
    dstore = DatasetStore(dsn, workspace_id)
    try:
        dataset_ids = sorted({v.dataset_id for v in dstore.list_versions(500)})
    finally:
        dstore.close()
    if not dataset_ids:
        return None

    pstore = ProfileStore(dsn, workspace_id)
    try:
        profiles = [p for did in dataset_ids if (p := pstore.latest(did)) is not None]
    finally:
        pstore.close()
    if not profiles:
        return None

    sstore = SemanticStore(dsn, workspace_id)
    try:
        semantic_profiles = {did: sstore.latest(did) for did in dataset_ids}
    finally:
        sstore.close()
    semantic_profiles = {k: v for k, v in semantic_profiles.items() if v is not None}

    gstore = GraphProfileStore(dsn, workspace_id)
    try:
        graph_profile = gstore.latest(f"graph_workspace_{workspace_id}")
    finally:
        gstore.close()

    intent = None
    from aryx.store.intent_store import IntentStore
    istore = IntentStore(dsn, workspace_id)
    try:
        recent = istore.list(1)
        intent = recent[0] if recent else None
    finally:
        istore.close()

    ctx = assemble_workspace_context(
        workspace_id=workspace_id, version="v1", dataset_profiles=profiles,
        semantic_profiles=semantic_profiles, graph_profile=graph_profile,
        intent=intent, operations=OPERATIONS, charts=CHARTS,
    )
    store = ContextStore(dsn, workspace_id)
    try:
        store.save(ctx)
    finally:
        store.close()
    logger.info("workspace planning context ws=%s datasets=%d status=%s cols=%d paths=%d",
                workspace_id, len(profiles), ctx.context_status,
                len(ctx.approved_columns), len(ctx.approved_graph_paths))
    return ctx
