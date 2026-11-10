"""What happens when the data behind the graph changes.

The graph is read live from the relational tables, so there is nothing to
rebuild. This replaces the old projection step: it clears the reasoning
engine's derived output (which may point at entities that were merged or
deleted, and is rebuilt on demand by ``POST /rules/evaluate``) and returns the
workspace's stored counts under the keys the projector used to report.
"""
from __future__ import annotations

import logging

from aryx.queries import load
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
    corrected or deleted.
    """
    with InferredStore(dsn, workspace_id) as store:
        store.clear()
    counts = graph_counts(dsn, workspace_id)
    logger.info("graph changed ws=%s %s", workspace_id, counts)
    return counts
