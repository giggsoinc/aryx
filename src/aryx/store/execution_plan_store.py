"""Persistence for compiled execution plans (C11).

Workspace-scoped. One row per (dataset_id, dataset_version); re-running
(a new C08 spec approval for the same version) replaces it in place — a
rejected compilation is auditable, not just a successful one.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.execution_compiler.models import ExecutionPlan
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class ExecutionPlanStore:
    """Reads and writes compiled execution plans for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, plan: ExecutionPlan) -> None:
        """Upsert a plan by (workspace_id, dataset_id, dataset_version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_execution_plan"),
                    (
                        self._ws, plan.execution_plan_id, plan.spec_id,
                        plan.dataset_id, plan.dataset_version,
                        len(plan.nodes), plan.compilation_status,
                        Json(plan.model_dump(mode="json")),
                    ),
                )
        logger.info("saved execution plan ws=%s dataset=%s status=%s nodes=%d",
                    self._ws, plan.dataset_id, plan.compilation_status, len(plan.nodes))

    def latest(self, dataset_id: str) -> ExecutionPlan | None:
        """Return the newest execution plan for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_execution_plan_latest"), (self._ws, dataset_id))
                row = cur.fetchone()
        return ExecutionPlan(**row[0]) if row else None

    def list(self, limit: int = 100) -> list[ExecutionPlan]:
        """Return recent execution plans across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_execution_plans"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [ExecutionPlan(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
