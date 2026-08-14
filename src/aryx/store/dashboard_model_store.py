"""Persistence for composed dashboard models (C14).

Workspace-scoped. One row per (dataset_id, dataset_version); re-running
replaces it in place, same convention as DashboardSpecStore/ExecutionPlanStore.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.dashboard_composition.models import DashboardModel
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class DashboardModelStore:
    """Reads and writes composed dashboard models for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, model: DashboardModel) -> None:
        """Upsert a dashboard model by (workspace_id, dataset_id, dataset_version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_dashboard_model"),
                    (
                        self._ws, model.dashboard_model_id, model.spec_id,
                        model.dataset_id, model.dataset_version,
                        len(model.sections), model.composition_status, model.composed_by,
                        Json(model.model_dump(mode="json")),
                    ),
                )
        logger.info("saved dashboard model ws=%s dataset=%s status=%s sections=%d",
                    self._ws, model.dataset_id, model.composition_status, len(model.sections))

    def latest(self, dataset_id: str) -> DashboardModel | None:
        """Return the newest dashboard model for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dashboard_model_latest"), (self._ws, dataset_id))
                row = cur.fetchone()
        return DashboardModel(**row[0]) if row else None

    def list(self, dataset_id: str, limit: int = 50) -> list[DashboardModel]:
        """Return recent dashboard models for one dataset, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_dashboard_models"), (self._ws, dataset_id, int(limit)))
                rows = cur.fetchall()
        return [DashboardModel(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
