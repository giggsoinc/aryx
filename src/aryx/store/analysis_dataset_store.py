"""Persistence for Preprocessing and Transformation records (C10).

Workspace-scoped. One row per (dataset_id, dataset_version); re-running
replaces it in place — this is a transformation LOG, not a versioned
immutable snapshot like C02/C05.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.preprocess.models import AnalysisDataset
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class AnalysisDatasetStore:
    """Reads and writes C10 transformation logs for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, result: AnalysisDataset) -> None:
        """Upsert by (workspace_id, source_dataset_id, source_dataset_version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_analysis_dataset"),
                    (
                        self._ws, result.analysis_dataset_id, result.source_dataset_id,
                        result.source_dataset_version, result.status, result.row_count,
                        Json(result.model_dump(mode="json")),
                    ),
                )
        logger.info("saved analysis dataset ws=%s dataset=%s status=%s",
                    self._ws, result.source_dataset_id, result.status)

    def latest(self, dataset_id: str) -> AnalysisDataset | None:
        """Return the most recent transformation log for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_analysis_dataset_latest"), (self._ws, dataset_id))
                row = cur.fetchone()
        return AnalysisDataset(**row[0]) if row else None

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
