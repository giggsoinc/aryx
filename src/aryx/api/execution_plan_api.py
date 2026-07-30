"""Execution Compiler API (C11) — read-only.

GET /execution-plan/{dataset_id}  — latest compiled plan for a dataset.
GET /execution-plan/versions      — list recent plans across the workspace.

Plans are produced automatically once C08's spec is approved (C09) — see
andie_planner.run._run_c11_for_dataset. No LLM, no run/POST endpoint here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from aryx.config import get_settings
from aryx.execution_compiler.models import ExecutionPlan
from aryx.store.execution_plan_store import ExecutionPlanStore

logger = logging.getLogger(__name__)


def execution_plan_router() -> APIRouter:
    """Build the Execution Compiler router."""
    router = APIRouter(prefix="/execution-plan")

    # Declared before /{dataset_id} so "versions" is not swallowed as an id.
    @router.get("/versions", response_model=list[ExecutionPlan])
    def list_plans(workspace_id: int = Query(1),
                   limit: int = Query(50, ge=1, le=500)) -> list[ExecutionPlan]:
        """List recent execution plans across the workspace, newest first."""
        store = ExecutionPlanStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.get("/{dataset_id}", response_model=ExecutionPlan)
    def get_plan(dataset_id: str, workspace_id: int = Query(1)) -> ExecutionPlan:
        """Fetch the latest compiled execution plan for a dataset."""
        store = ExecutionPlanStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, f"no execution plan for {dataset_id!r}")
        return latest

    return router
