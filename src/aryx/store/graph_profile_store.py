"""Persistence for graph profiles (C06).

Workspace-scoped. The full GraphProfile document is stored as JSONB, one row per
(graph_id, graph_version); re-profiling replaces it in place.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.graph_profiler.models import GraphProfile
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class GraphProfileStore:
    """Reads and writes graph profiles for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, profile: GraphProfile) -> None:
        """Upsert a graph profile by (workspace_id, graph_id, graph_version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_graph_profile"),
                    (
                        self._ws, profile.graph_profile_id, profile.graph_id,
                        profile.graph_version, profile.entity_count,
                        profile.relationship_count, len(profile.verified_paths),
                        profile.profile_status, Json(profile.model_dump(mode="json")),
                    ),
                )
        logger.info("saved graph profile ws=%s id=%s paths=%d",
                    self._ws, profile.graph_profile_id, len(profile.verified_paths))

    def latest(self, graph_id: str) -> GraphProfile | None:
        """Return the newest graph profile for a graph, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_graph_profile_latest"), (self._ws, graph_id))
                row = cur.fetchone()
        return GraphProfile(**row[0]) if row else None

    def list(self, limit: int = 50) -> list[GraphProfile]:
        """Return recent graph profiles across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_graph_profiles"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [GraphProfile(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
