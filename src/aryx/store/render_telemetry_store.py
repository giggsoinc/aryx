"""Persistence for frontend render telemetry (C15).

Workspace-scoped, insert-only — each render is a distinct, independently
timed event (same convention as ExecutionRunStore), not a versioned
artifact to upsert in place.
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from aryx.dashboard_render.models import RenderTelemetry
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class RenderTelemetryStore:
    """Reads and writes render telemetry for one workspace."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared pool + bind a workspace for every call."""
        self._pool = get_pool(dsn)
        self._ws = int(workspace_id)

    def save(self, telemetry: RenderTelemetry) -> None:
        """Insert one render event."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    load("insert_render_telemetry"),
                    (
                        self._ws, telemetry.render_id, telemetry.dashboard_model_id,
                        telemetry.render_status, telemetry.rendered_component_count,
                        telemetry.warning_count, Json(telemetry.unsupported_component_types),
                        Json(telemetry.accessibility_checks.model_dump(mode="json")),
                    ),
                )
        logger.info("saved render telemetry ws=%s dashboard=%s status=%s",
                    self._ws, telemetry.dashboard_model_id, telemetry.render_status)

    def list(self, dashboard_model_id: str, limit: int = 50) -> list[dict]:
        """Return recent render events for one dashboard model, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("list_render_telemetry"), (self._ws, dashboard_model_id, int(limit)))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
