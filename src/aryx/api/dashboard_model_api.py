"""Dashboard Composition API (C14) — on-demand, never auto-run.

POST /dashboard-model/run       — compose the dashboard model for a dataset.
GET  /dashboard-model/workspace — latest model for the whole workspace.
GET  /dashboard-model/versions  — list recent models across the workspace.

On-demand only, like C08/C12: composition is gated on C13's
eligible_for_dashboard and never runs automatically.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.dashboard_composition.models import DashboardModel
from aryx.dashboard_composition.run import compose_dashboard
from aryx.llm import complete_json
from aryx.store.dashboard_model_store import DashboardModelStore

logger = logging.getLogger(__name__)


class DashboardComposeRequest(BaseModel):
    dataset_id: str
    audience: str = ""
    maximum_columns: int = 3
    maximum_primary_charts: int | None = None
    use_llm: bool = False
    tier: str = "cheap"


def dashboard_model_router() -> APIRouter:
    """Build the Dashboard Composition router."""
    router = APIRouter(prefix="/dashboard-model")

    @router.post("/run", response_model=DashboardModel)
    def run(req: DashboardComposeRequest, workspace_id: int = Query(1)) -> DashboardModel:
        """Compose the dashboard model for `dataset_id` and persist it."""
        broker = None
        if req.use_llm:
            from aryx.api.admin_api import _local_broker
            broker = _local_broker()
        return compose_dashboard(
            get_settings().rdb_dsn, workspace_id, req.dataset_id,
            audience=req.audience, maximum_columns=req.maximum_columns,
            maximum_primary_charts=req.maximum_primary_charts,
            use_llm=req.use_llm, tier=req.tier, broker=broker, complete_json_fn=complete_json,
        )

    @router.get("/workspace", response_model=DashboardModel | None)
    def latest_workspace_model(workspace_id: int = Query(1)) -> DashboardModel | None:
        """Fetch the latest composed dashboard for the whole workspace, or null."""
        store = DashboardModelStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.latest(f"workspace_{workspace_id}")
        finally:
            store.close()

    @router.get("/versions", response_model=list[DashboardModel])
    def list_models(dataset_id: str = Query(...), workspace_id: int = Query(1),
                    limit: int = Query(50, ge=1, le=500)) -> list[DashboardModel]:
        """List recent composed dashboards for one dataset, newest first."""
        store = DashboardModelStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(dataset_id, limit)
        finally:
            store.close()

    return router
