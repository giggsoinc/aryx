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

from aryx.andie_planner.delta import confirm_delta, draft_delta
from aryx.andie_planner.models import Analysis, DeltaDraftResult, Kpi, PlannerResult, Visualization
from aryx.andie_planner.run import run_planner, run_planner_workspace
from aryx.config import get_settings
from aryx.llm import complete_json
from aryx.store.context_store import ContextStore
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


class DeltaDraftRequest(BaseModel):
    dataset_id: str
    request_text: str
    tier: str = "frontier"


class DeltaConfirmRequest(BaseModel):
    dataset_id: str
    new_kpi: Kpi | None = None
    new_analysis: Analysis | None = None
    new_visualization: Visualization | None = None


def andie_planner_router() -> APIRouter:
    """Build the Andie Jr Planning Orchestrator router."""
    router = APIRouter(prefix="/andie-planner")

    @router.post("/run", response_model=PlannerResult)
    def run(req: PlannerRunRequest, workspace_id: int = Query(1)) -> PlannerResult:
        """Draft, ground, and persist a candidate dashboard spec."""
        logger.info("andie-planner run request ws=%s dataset=%s tier=%s",
                   workspace_id, req.dataset_id, req.tier)
        result = run_planner(
            get_settings().rdb_dsn, workspace_id, req.dataset_id,
            objective=req.objective, target_audience=req.target_audience,
            tier=req.tier,
        )
        if result.status != "valid":
            logger.warning("andie-planner run ws=%s dataset=%s ended status=%s error_code=%s",
                          workspace_id, req.dataset_id, result.status, result.error_code)
        return result

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
        logger.info("andie-planner workspace run request ws=%s tier=%s", workspace_id, req.tier)
        result = run_planner_workspace(
            get_settings().rdb_dsn, workspace_id,
            objective=req.objective, target_audience=req.target_audience, tier=req.tier,
        )
        if result.status != "valid":
            logger.warning("andie-planner workspace run ws=%s ended status=%s error_code=%s",
                          workspace_id, result.status, result.error_code)
        return result

    @router.get("/workspace", response_model=PlannerResult)
    def get_workspace_result(workspace_id: int = Query(1)) -> PlannerResult:
        """Fetch the latest workspace-wide planning result."""
        store = DashboardSpecStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(f"workspace_{workspace_id}")
        finally:
            store.close()
        if latest is None:
            logger.info("no workspace-wide planning result yet ws=%s", workspace_id)
            raise HTTPException(404, "no workspace-wide planning result yet")
        return latest

    @router.post("/delta/draft", response_model=DeltaDraftResult)
    def draft(req: DeltaDraftRequest, workspace_id: int = Query(1)) -> DeltaDraftResult:
        """Ask-to-visualize, step 1: draft ONE new chart against the dataset's/
        workspace's latest approved spec. Never persists, never chains
        execution/composition — the caller shows this as a preview first."""
        dsn = get_settings().rdb_dsn
        spec_store = DashboardSpecStore(dsn, workspace_id)
        try:
            latest = spec_store.latest(req.dataset_id)
        finally:
            spec_store.close()
        if latest is None or latest.spec is None:
            return DeltaDraftResult(status="controlled_error", error_code="no_approved_spec",
                                    error_message=f"no approved spec to extend for {req.dataset_id!r}")

        cstore = ContextStore(dsn, workspace_id)
        try:
            ctx = cstore.latest(req.dataset_id)
        finally:
            cstore.close()
        if ctx is None:
            return DeltaDraftResult(status="controlled_error", error_code="no_planning_context",
                                    error_message=f"no planning context for {req.dataset_id!r}")

        from aryx.api.admin_api import _local_broker
        return draft_delta(latest.spec, ctx, req.request_text, broker=_local_broker(),
                           tier=req.tier, complete_json_fn=complete_json)

    @router.post("/delta/confirm", response_model=PlannerResult)
    def confirm(req: DeltaConfirmRequest, workspace_id: int = Query(1)) -> PlannerResult:
        """Ask-to-visualize, step 2: re-validate (never trust the client-echoed
        draft), persist, and chain C10->C11->C12->C13->C14 — the chart
        appears in the dashboard after this one call."""
        return confirm_delta(
            get_settings().rdb_dsn, workspace_id, req.dataset_id,
            new_kpi=req.new_kpi, new_analysis=req.new_analysis,
            new_visualization=req.new_visualization,
        )

    @router.get("/{dataset_id}", response_model=PlannerResult)
    def get_result(dataset_id: str, workspace_id: int = Query(1)) -> PlannerResult:
        """Fetch the latest planning result for a dataset."""
        store = DashboardSpecStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            logger.info("no planning result found for dataset=%s ws=%s", dataset_id, workspace_id)
            raise HTTPException(404, f"no planning result for dataset {dataset_id!r}")
        return latest

    return router
