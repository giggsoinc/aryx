"""Durable ingestion-job tracking: live stage progress + 30-day retention.

SQL lives in aryx/queries/*.sql (DB-Guard discipline). Each ingest creates a
job; the pipeline reports stage/% which is persisted as both current state and
an append-only event log (feeds the observability dashboard).
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg

from aryx.queries import load

logger = logging.getLogger(__name__)

_COLUMNS = ["job_id", "source_system", "source_dataset", "status", "stage",
            "pct", "detail", "run_id", "error", "started_at", "updated_at",
            "finished_at"]


def _row(values: tuple) -> dict[str, Any]:
    return {col: val for col, val in zip(_COLUMNS, values)}


class JobStore:
    """Persists ingestion jobs and their per-stage progress to Postgres."""

    def __init__(self, dsn: str) -> None:
        """Open an autocommit connection so progress is visible mid-run."""
        self._conn = psycopg.connect(dsn, autocommit=True)

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def create(self, job_id: str, system: str, dataset: str) -> None:
        """Open a queued job row."""
        with self._conn.cursor() as cur:
            cur.execute(load("insert_job"), (job_id, system, dataset))

    def update_stage(self, job_id: str, stage: str, pct: int, detail: str) -> None:
        """Record the current stage and append it to the event log."""
        with self._conn.cursor() as cur:
            cur.execute(load("update_job_stage"), (stage, pct, detail, job_id))
            cur.execute(load("insert_job_event"), (job_id, stage, pct, detail))

    def finish(self, job_id: str, run_id: int | None, status: str,
               error: str | None = None) -> None:
        """Mark a job complete or failed."""
        with self._conn.cursor() as cur:
            cur.execute(load("finish_job"), (status, run_id, error, job_id))

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Return one job's current state, or None."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_job"), (job_id,))
            row = cur.fetchone()
        return _row(row) if row else None

    def list_recent(self) -> list[dict[str, Any]]:
        """Return the most recent jobs (newest first)."""
        with self._conn.cursor() as cur:
            cur.execute(load("select_recent_jobs"))
            return [_row(r) for r in cur.fetchall()]

    def archive_old(self, days: int = 30) -> int:
        """Archive then purge finished jobs (and old events) older than `days`.

        Returns the number of live job rows deleted.
        """
        with self._conn.cursor() as cur:
            cur.execute(load("archive_old_jobs"), (days,))
            cur.execute(load("delete_old_jobs"), (days,))
            deleted = cur.rowcount
            cur.execute(load("delete_old_job_events"), (days,))
        logger.info("archived/purged jobs older than %d days: %d", days, deleted)
        return deleted
