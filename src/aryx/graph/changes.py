"""What happens when the data behind the graph changes.

The graph is read live from the relational tables, so there is nothing to
rebuild. This replaces the old projection step: it clears the reasoning
engine's derived output (which may point at entities that were merged or
deleted, and is rebuilt on demand by ``POST /rules/evaluate``) and returns the
workspace's stored counts under the keys the projector used to report.
"""
from __future__ import annotations

import logging
import time

from aryx.graph import overview_cache
from aryx.job_cancel import checkpoint
from aryx.queries import load
from aryx.raven_log_config import log as raven_log
from aryx.store.inferred_store import InferredStore
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

_COUNT_QUERIES = (
    ("entities", "count_entities"),
    ("provenance", "count_members_provenance"),
    ("relationships", "count_relationships"),
)


def graph_counts(dsn: str, workspace_id: int) -> dict[str, int]:
    """Stored entity, provenance and relationship row counts for a workspace."""
    counts: dict[str, int] = {}
    with get_pool(dsn).connection() as conn:
        with conn.cursor() as cur:
            for key, query in _COUNT_QUERIES:
                cur.execute(load(query), (int(workspace_id),))
                counts[key] = int(cur.fetchone()[0])
    return counts


def after_graph_change(dsn: str, workspace_id: int) -> dict[str, int]:
    """Invalidate derived graph output and return the workspace's counts.

    Call wherever entities or relationships were just written, merged,
    corrected or deleted. Besides the reasoning engine's output it drops the
    cached Ask overview for the workspace, so the next question sees the new
    totals instead of waiting out the cache TTL.

    Write guard: inside a job's cancel_scope this raises JobCancelled BEFORE
    touching the database when the job was cancelled or its workspace was
    deleted / re-created since the run started, so a stale run can never clear
    derived output in a workspace that now owns the same id.
    """
    checkpoint(force=True)
    started = time.monotonic()
    with InferredStore(dsn, workspace_id) as store:
        store.clear()
    overview_cache.invalidate(workspace_id)
    counts = graph_counts(dsn, workspace_id)
    logger.info("graph changed ws=%s %s", workspace_id, counts)
    raven_log(
        "DEBUG", "graph changed; derived output cleared and Ask overview invalidated",
        criticality="P4", service="aryx-api", error_code="GRAPH_CHANGE_APPLIED",
        context={"object_id": "graph", "workspace_id": workspace_id,
                 "task_id": f"graph-change-{workspace_id}",
                 "trace_id": f"graph-change-{workspace_id}",
                 "dependency_name": "ask_overview_cache", "operation": "invalidate",
                 "attempt": 1, "error_class": "",
                 "duration_ms": int((time.monotonic() - started) * 1000),
                 "final_status": "applied", "result": "invalidated",
                 "reason_code": "GRAPH_CHANGE_APPLIED", "stage": "GraphChange",
                 "impact_scope": "ask_overview"})
    return counts
