"""Persistence for deterministic analysis execution runs (C12).

Workspace-scoped, insert-only (unlike C08-C11's upsert-in-place versioning)
— each trigger is a genuinely new, independently timed run; history is kept
rather than overwritten (see migration 0039's comment).
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.analysis_execution.models import ExecutionRun
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class ExecutionRunStore:
    """Reads and writes analysis execution runs for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, run: ExecutionRun) -> None:
        """Insert one execution run."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_execution_run"),
                    (
                        self._ws, run.execution_run_id, run.execution_plan_id,
                        run.spec_id, run.dataset_id, run.dataset_version, run.status,
                        len(run.kpi_results), len(run.analysis_results),
                        Json(run.model_dump(mode="json")),
                    ),
                )
        logger.info("saved execution run ws=%s dataset=%s status=%s",
                    self._ws, run.dataset_id, run.status)

    def latest(self, dataset_id: str) -> ExecutionRun | None:
        """Return the newest execution run for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_execution_run_latest"), (self._ws, dataset_id))
                row = cur.fetchone()
        return ExecutionRun(**row[0]) if row else None

    def list(self, dataset_id: str, limit: int = 50) -> list[ExecutionRun]:
        """Return recent execution runs for a dataset, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_execution_runs"), (self._ws, dataset_id, int(limit)))
                rows = cur.fetchall()
        return [ExecutionRun(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
