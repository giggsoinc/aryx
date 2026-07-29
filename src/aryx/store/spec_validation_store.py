"""Persistence for Pre-Execution Specification Validation records (C09).

Workspace-scoped. Every attempt (approved or rejected) is persisted — the
persisted attempt COUNT is what enforces the single-retry cap server-side,
independent of whether the caller behaves (see spec_validation/run.py).
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.queries import load
from aryx.spec_validation.models import ValidationReport
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class SpecValidationStore:
    """Reads and writes C09 validation attempts for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, report: ValidationReport, spec_id: str = "") -> None:
        """Upsert one validation attempt by (workspace_id, validation_id, attempt)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_spec_validation"),
                    (
                        self._ws, report.validation_id, report.attempt, spec_id,
                        report.status, Json(report.model_dump(mode="json")),
                    ),
                )
        logger.info("saved spec validation ws=%s validation_id=%s attempt=%d status=%s",
                    self._ws, report.validation_id, report.attempt, report.status)

    def count_attempts(self, validation_id: str) -> int:
        """Number of attempts already persisted for this validation_id."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("count_spec_validation_attempts"), (self._ws, validation_id))
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def latest(self, validation_id: str) -> ValidationReport | None:
        """Return the most recent validation attempt, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_spec_validation_latest"), (self._ws, validation_id))
                row = cur.fetchone()
        return ValidationReport(**row[0]) if row else None

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
