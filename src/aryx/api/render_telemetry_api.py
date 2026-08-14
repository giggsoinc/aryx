"""Frontend Dashboard Renderer telemetry API (C15).

POST /render-telemetry/log   — record one render event from the frontend.
GET  /render-telemetry/list  — recent render events for a dashboard model.

An audit trail only — nothing here gates or alters rendering; the frontend
renders first, then reports what happened. No LLM, no compute.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from aryx.config import get_settings
from aryx.dashboard_render.models import RenderTelemetry
from aryx.store.render_telemetry_store import RenderTelemetryStore

logger = logging.getLogger(__name__)


def render_telemetry_router() -> APIRouter:
    """Build the Frontend Dashboard Renderer telemetry router."""
    router = APIRouter(prefix="/render-telemetry")

    @router.post("/log")
    def log(telemetry: RenderTelemetry, workspace_id: int = Query(1)) -> dict[str, str]:
        """Record one render event."""
        if telemetry.render_status != "success" or telemetry.unsupported_component_types:
            logger.warning(
                "render reported ws=%s dashboard=%s status=%s unsupported=%s accessibility=%s",
                workspace_id, telemetry.dashboard_model_id, telemetry.render_status,
                telemetry.unsupported_component_types, telemetry.accessibility_checks)
        store = RenderTelemetryStore(get_settings().rdb_dsn, workspace_id)
        try:
            store.save(telemetry)
        finally:
            store.close()
        return {"status": "logged"}

    @router.get("/list")
    def list_events(dashboard_model_id: str = Query(...), workspace_id: int = Query(1),
                    limit: int = Query(50, ge=1, le=500)) -> list[dict]:
        """List recent render events for one dashboard model."""
        store = RenderTelemetryStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(dashboard_model_id, limit)
        finally:
            store.close()

    return router
