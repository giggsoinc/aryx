"""Glue: profile a workspace's validated graph and persist it (C06).

Shared by the ingest auto-trigger, backfill, and API. Loads the latest C05
validated graph, profiles it, and saves the graph profile. The user objective
(for path relevance) is resolved best-effort from the workspace's latest intent.
"""
from __future__ import annotations

import logging

from aryx.graph_profiler.models import GraphProfile
from aryx.graph_profiler.profile import profile_graph
from aryx.store.graph_intake_store import GraphIntakeStore
from aryx.store.graph_profile_store import GraphProfileStore

logger = logging.getLogger(__name__)


def _resolve_objective(dsn: str, workspace_id: int) -> str:
    """Best-effort: most recent C01 intent objective for path relevance."""
    try:
        from aryx.store.intent_store import IntentStore
        store = IntentStore(dsn, workspace_id)
        try:
            recent = store.list(1)
        finally:
            store.close()
        return recent[0].objective if recent else ""
    except Exception:  # noqa: BLE001 — objective is only a relevance hint
        return ""


def run_graph_profile(dsn: str, workspace_id: int, graph_id: str | None = None,
                      *, user_objective: str | None = None,
                      max_depth: int = 3) -> GraphProfile | None:
    """Profile the workspace's latest validated graph and persist the profile."""
    graph_id = graph_id or f"graph_workspace_{workspace_id}"
    store = GraphIntakeStore(dsn, workspace_id)
    try:
        latest = store.latest(graph_id)
        if latest is None:
            return None
        normalized = store.full_normalized(graph_id)
    finally:
        store.close()

    objective = user_objective if user_objective is not None else _resolve_objective(dsn, workspace_id)
    prof = profile_graph(
        normalized, graph_id, latest.graph_version,
        user_objective=objective, max_depth=max_depth,
        graph_valid=(latest.schema_status == "valid"),
    )
    pstore = GraphProfileStore(dsn, workspace_id)
    try:
        pstore.save(prof)
    finally:
        pstore.close()
    logger.info("graph profile ws=%s graph=%s version=%s types=%d paths=%d",
                workspace_id, graph_id, prof.graph_version,
                len(prof.entity_types), len(prof.verified_paths))
    return prof
