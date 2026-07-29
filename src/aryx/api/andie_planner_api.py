"""Andie Jr Planning Orchestrator API (C08) — on-demand, never auto-run.

POST /andie-planner/run           — draft + ground a dashboard spec for a dataset.
GET  /andie-planner/versions      — list recent planning results.
GET  /andie-planner/{dataset_id}  — latest planning result for a dataset.

On-demand only (not chained into ingestion like C02-C07): this is the first
component that calls a real LLM, so every run has real cost/latency.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aryx.andie_planner.models import PlannerResult
from aryx.andie_planner.run import run_planner, run_planner_workspace
from aryx.config import get_settings
from aryx.store.dashboard_spec_store import DashboardSpecStore

logger = logging.getLogger(__name__)


class PlannerRunRequest(BaseModel):
    dataset_id: str
    objective: str | None = None
    target_audience: str | None = None
    tier: str = "frontier"


class WorkspacePlannerRunRequest(BaseModel):
    objective: str | None = None
    target_audience: str | None = None
    tier: str = "frontier"


def andie_planner_router() -> APIRouter:
    """Build the Andie Jr Planning Orchestrator router."""
    router = APIRouter(prefix="/andie-planner")

    @router.post("/run", response_model=PlannerResult)
    def run(req: PlannerRunRequest, workspace_id: int = Query(1)) -> PlannerResult:
        """Draft, ground, and persist a candidate dashboard spec."""
        return run_planner(
            get_settings().rdb_dsn, workspace_id, req.dataset_id,
            objective=req.objective, target_audience=req.target_audience,
            tier=req.tier,
        )

    # Declared before /{dataset_id} so "versions"/"workspace" are not
    # swallowed as a dataset_id path param.
    @router.get("/versions", response_model=list[PlannerResult])
    def list_results(workspace_id: int = Query(1),
                     limit: int = Query(50, ge=1, le=500)) -> list[PlannerResult]:
        """List recent planning results, newest first."""
        store = DashboardSpecStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.post("/workspace/run", response_model=PlannerResult)
    def run_workspace(req: WorkspacePlannerRunRequest,
                      workspace_id: int = Query(1)) -> PlannerResult:
        """Draft, ground, and persist a dashboard spec spanning the WHOLE workspace."""
        return run_planner_workspace(
            get_settings().rdb_dsn, workspace_id,
            objective=req.objective, target_audience=req.target_audience, tier=req.tier,
        )

    @router.get("/workspace", response_model=PlannerResult)
    def get_workspace_result(workspace_id: int = Query(1)) -> PlannerResult:
        """Fetch the latest workspace-wide planning result."""
        store = DashboardSpecStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(f"workspace_{workspace_id}")
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, "no workspace-wide planning result yet")
        return latest

    @router.get("/{dataset_id}", response_model=PlannerResult)
    def get_result(dataset_id: str, workspace_id: int = Query(1)) -> PlannerResult:
        """Fetch the latest planning result for a dataset."""
        store = DashboardSpecStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, f"no planning result for dataset {dataset_id!r}")
        return latest

    return router
