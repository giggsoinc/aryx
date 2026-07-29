"""Persistence for planning contexts (C07).

Workspace-scoped. The full PlanningContext document is stored as JSONB, one row
per (dataset_id, dataset_version); re-assembling replaces it in place.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.planning.models import PlanningContext
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class ContextStore:
    """Reads and writes planning contexts for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, ctx: PlanningContext) -> None:
        """Upsert a planning context by (workspace_id, dataset_id, version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_planning_context"),
                    (
                        self._ws, ctx.planning_context_id, ctx.dataset_id,
                        ctx.dataset_version, ctx.context_status,
                        len(ctx.approved_columns), Json(ctx.model_dump(mode="json")),
                    ),
                )
        logger.info("saved planning context ws=%s id=%s status=%s cols=%d",
                    self._ws, ctx.planning_context_id, ctx.context_status,
                    len(ctx.approved_columns))

    def latest(self, dataset_id: str) -> PlanningContext | None:
        """Return the newest planning context for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_planning_context_latest"),
                            (self._ws, dataset_id))
                row = cur.fetchone()
        return PlanningContext(**row[0]) if row else None

    def list(self, limit: int = 100) -> list[PlanningContext]:
        """Return recent planning contexts across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_planning_contexts"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [PlanningContext(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
