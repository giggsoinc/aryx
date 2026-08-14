"""Deterministic Analysis Execution API (C12) — on-demand, never auto-run.

POST /execution-run/run       — execute the latest compiled plan for a dataset.
GET  /execution-run/workspace — latest run for the whole workspace.
GET  /execution-run/versions  — list recent runs for a dataset.

On-demand only, like C08: this is the first component after C08 to do real
work on request rather than being chained onto an approval — triggered
explicitly, never automatically.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from aryx.analysis_execution.models import ExecutionRun
from aryx.analysis_execution.run import run_analysis_execution
from aryx.config import get_settings
from aryx.store.execution_run_store import ExecutionRunStore

logger = logging.getLogger(__name__)

# Hard server-side ceilings — a caller can ask for LESS than these, never
# more. Without them, maximum_runtime_seconds/maximum_rows were unbounded
# client input straight into an in-memory computation: a caller could hang
# the process for as long as they liked over as many rows as they liked.
_MAX_RUNTIME_SECONDS_CEILING = 30.0
_MAX_ROWS_CEILING = 50_000


class ExecutionRunRequest(BaseModel):
    dataset_id: str
    maximum_runtime_seconds: float = Field(default=30.0, gt=0, le=_MAX_RUNTIME_SECONDS_CEILING)
    maximum_rows: int = Field(default=50_000, gt=0, le=_MAX_ROWS_CEILING)


def execution_run_router() -> APIRouter:
    """Build the Deterministic Analysis Execution router."""
    router = APIRouter(prefix="/execution-run")

    @router.post("/run", response_model=ExecutionRun)
    def run(req: ExecutionRunRequest, workspace_id: int = Query(1)) -> ExecutionRun:
        """Execute the latest compiled plan for `dataset_id` and persist the run."""
        logger.info("execution-run requested ws=%s dataset=%s max_runtime=%.1fs max_rows=%d",
                   workspace_id, req.dataset_id, req.maximum_runtime_seconds, req.maximum_rows)
        result = run_analysis_execution(
            get_settings().rdb_dsn, workspace_id, req.dataset_id,
            maximum_runtime_seconds=req.maximum_runtime_seconds,
            maximum_rows=req.maximum_rows,
        )
        if result.status != "completed":
            logger.warning("execution-run finished ws=%s dataset=%s status=%s errors=%s",
                          workspace_id, req.dataset_id, result.status, result.errors)
        return result

    # Declared before /{dataset_id}-shaped routes aren't needed here since
    # every read is dataset_id-scoped via query — "workspace" is its own path.
    @router.get("/workspace", response_model=ExecutionRun | None)
    def latest_workspace_run(workspace_id: int = Query(1)) -> ExecutionRun | None:
        """Fetch the latest execution run for the whole workspace, or null."""
        store = ExecutionRunStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(f"workspace_{workspace_id}")
        finally:
            store.close()
        if latest is None:
            logger.info("no execution run found ws=%s", workspace_id)
        return latest

    @router.get("/versions", response_model=list[ExecutionRun])
    def list_runs(dataset_id: str = Query(...), workspace_id: int = Query(1),
                  limit: int = Query(50, ge=1, le=500)) -> list[ExecutionRun]:
        """List recent execution runs for one dataset, newest first."""
        store = ExecutionRunStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(dataset_id, limit)
        finally:
            store.close()

    return router
