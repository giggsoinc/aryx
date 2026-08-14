"""Persistence for Andie Jr planning results (C08).

Workspace-scoped. Stores the full PlannerResult (valid spec OR a controlled
error) as JSONB, one row per (dataset_id, dataset_version); re-running replaces
it in place — a failed attempt is auditable, not just a successful one.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.andie_planner.models import PlannerResult
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class DashboardSpecStore:
    """Reads and writes Andie planning results for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, result: PlannerResult, dataset_id: str, dataset_version: str) -> None:
        """Upsert a planning result by (workspace_id, dataset_id, version)."""
        spec_id = result.spec.spec_id if result.spec else f"dashboard_spec_{dataset_id}_{dataset_version}"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_dashboard_spec"),
                    (
                        self._ws, spec_id, dataset_id, dataset_version, result.status,
                        result.error_code or "",
                        len(result.spec.kpis) if result.spec else 0,
                        len(result.spec.warnings) if result.spec else 0,
                        Json(result.model_dump(mode="json")),
                    ),
                )
        logger.info("saved dashboard spec ws=%s dataset=%s status=%s",
                    self._ws, dataset_id, result.status)

    def latest(self, dataset_id: str) -> PlannerResult | None:
        """Return the newest planning result for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dashboard_spec_latest"), (self._ws, dataset_id))
                row = cur.fetchone()
        return PlannerResult(**row[0]) if row else None

    def list(self, limit: int = 100) -> list[PlannerResult]:
        """Return recent planning results across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_dashboard_specs"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [PlannerResult(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
