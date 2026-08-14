"""Persistence for dataset profiles (C03).

Workspace-scoped. The full DatasetProfile document is stored as JSONB, one row
per (dataset_id, dataset_version); re-profiling replaces it in place.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.profiler.models import DatasetProfile
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class ProfileStore:
    """Reads and writes dataset profiles for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, profile: DatasetProfile) -> None:
        """Upsert a profile by (workspace_id, dataset_id, dataset_version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_dataset_profile"),
                    (
                        self._ws, profile.dataset_profile_id, profile.dataset_id,
                        profile.dataset_version, profile.row_count,
                        profile.column_count, profile.profile_status,
                        Json(profile.model_dump(mode="json")),
                    ),
                )
        logger.info("saved profile ws=%s id=%s cols=%d",
                    self._ws, profile.dataset_profile_id, profile.column_count)

    def get(self, dataset_id: str, version: str) -> DatasetProfile | None:
        """Return the profile for a specific dataset version, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dataset_profile"),
                            (self._ws, dataset_id, version))
                row = cur.fetchone()
        return DatasetProfile(**row[0]) if row else None

    def latest(self, dataset_id: str) -> DatasetProfile | None:
        """Return the newest profile for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_dataset_profile_latest"),
                            (self._ws, dataset_id))
                row = cur.fetchone()
        return DatasetProfile(**row[0]) if row else None

    def list(self, limit: int = 100) -> list[DatasetProfile]:
        """Return recent profiles across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_dataset_profiles"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [DatasetProfile(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
