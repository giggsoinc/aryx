"""Persistence for User Intent Capture records (C01).

Workspace-scoped. Stores every capture attempt keyed by its correlation id;
re-capturing the same request_id updates the row in place (created_at is kept).
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.intent.models import BriefContext, IntentPreferences, UserIntent
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class IntentStore:
    """Reads and writes user_intent capture records for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, intent: UserIntent) -> None:
        """Upsert a capture record by (workspace_id, request_id)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_user_intent"),
                    (
                        self._ws, intent.request_id, intent.schema_version,
                        intent.uploaded_file, intent.domain, intent.objective,
                        Json(intent.brief_context.model_dump()),
                        Json(intent.preferences.model_dump()),
                        intent.validation_status,
                        Json(intent.warnings), Json(intent.errors),
                    ),
                )
        logger.info("saved user_intent ws=%s request_id=%s status=%s",
                    self._ws, intent.request_id, intent.validation_status)

    def get(self, request_id: str) -> UserIntent | None:
        """Return one capture record by correlation id, or None."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_user_intent"), (self._ws, request_id))
                row = cur.fetchone()
        return _row_to_intent(row) if row else None

    def list(self, limit: int = 50) -> list[UserIntent]:
        """Return recent capture records for the workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_user_intents"), (self._ws, int(limit)))
                rows = cur.fetchall()
        return [_row_to_intent(r) for r in rows]

    def has_valid_intent(self) -> bool:
        """True once at least one valid capture exists for this workspace.

        Gates the C03-C07 downstream pipeline (see aryx.pipeline.downstream) —
        that computation waits for a valid intent, not just any attempt.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_intent_valid_exists"), (self._ws,))
                row = cur.fetchone()
        return bool(row and row[0])

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""


def _row_to_intent(row: tuple) -> UserIntent:
    """Rebuild a UserIntent from a stored row."""
    return UserIntent(
        request_id=row[0],
        schema_version=row[1],
        uploaded_file=row[2],
        domain=row[3],
        objective=row[4],
        preferences=IntentPreferences(**(row[5] or {})),
        validation_status=row[6],
        warnings=row[7] or [],
        errors=row[8] or [],
        created_at=row[9],
        # Appended last so pre-0045 rows (which have no column) still map.
        brief_context=BriefContext(**(row[10] or {})) if len(row) > 10
        else BriefContext(),
    )
