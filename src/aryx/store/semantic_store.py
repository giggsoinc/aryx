"""Persistence for semantic profiles (C04).

Workspace-scoped. The full SemanticProfile document is stored as JSONB, one row
per (dataset_id, dataset_version); re-interpreting replaces it in place.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.queries import load
from aryx.semantic.models import SemanticProfile
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class SemanticStore:
    """Reads and writes semantic profiles for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, profile: SemanticProfile) -> None:
        """Upsert a semantic profile by (workspace_id, dataset_id, version)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("upsert_semantic_profile"),
                    (
                        self._ws, profile.semantic_profile_id, profile.dataset_id,
                        profile.dataset_version, profile.domain,
                        len(profile.annotations), len(profile.unresolved_fields),
                        profile.profile_status,
                        Json(profile.model_dump(mode="json")),
                    ),
                )
        logger.info("saved semantic profile ws=%s id=%s annotations=%d unresolved=%d",
                    self._ws, profile.semantic_profile_id,
                    len(profile.annotations), len(profile.unresolved_fields))

    def get(self, dataset_id: str, version: str) -> SemanticProfile | None:
        """Return the semantic profile for a dataset version, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_semantic_profile"),
                            (self._ws, dataset_id, version))
                row = cur.fetchone()
        return SemanticProfile(**row[0]) if row else None

    def latest(self, dataset_id: str) -> SemanticProfile | None:
        """Return the newest semantic profile for a dataset, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_semantic_profile_latest"),
                            (self._ws, dataset_id))
                row = cur.fetchone()
        return SemanticProfile(**row[0]) if row else None

    def list(self, limit: int = 100) -> list[SemanticProfile]:
        """Return recent semantic profiles across the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_semantic_profiles"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [SemanticProfile(**r[0]) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
