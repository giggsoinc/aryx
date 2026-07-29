"""Context and Resource Retrieval API (C07).

POST /planning-context/run              — assemble a dataset's planning context.
GET  /planning-context/versions         — list recent planning contexts.
POST /planning-context/workspace/run    — assemble the WHOLE workspace's context.
GET  /planning-context/workspace        — latest workspace-wide context.
GET  /planning-context/{dataset_id}     — latest planning context for a dataset.

Contexts are produced automatically after the graph profile (C06). Each package
contains only approved columns, graph paths, operations, and charts. The
workspace-wide context merges every dataset's columns, namespaced per dataset
(never flattened — see planning.models.DatasetColumns for why).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.planning.models import PlanningContext
from aryx.planning.run import run_context, run_workspace_context
from aryx.store.context_store import ContextStore

logger = logging.getLogger(__name__)


class ContextRunRequest(BaseModel):
    dataset_id: str
    dataset_version: str | None = None


def planning_context_router() -> APIRouter:
    """Build the Context and Resource Retrieval router."""
    router = APIRouter(prefix="/planning-context")

    @router.post("/run", response_model=PlanningContext)
    def run(req: ContextRunRequest, workspace_id: int = Query(1)) -> PlanningContext:
        """Assemble and persist a dataset's planning context."""
        ctx = run_context(get_settings().rdb_dsn, workspace_id,
                          req.dataset_id, req.dataset_version)
        if ctx is None:
            raise HTTPException(404, f"no profile for dataset {req.dataset_id!r}")
        return ctx

    # Declared before /{dataset_id} so "versions"/"workspace" are not
    # swallowed as a dataset_id path param.
    @router.get("/versions", response_model=list[PlanningContext])
    def list_contexts(workspace_id: int = Query(1),
                      limit: int = Query(100, ge=1, le=500)) -> list[PlanningContext]:
        """List recent planning contexts, newest first."""
        store = ContextStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.post("/workspace/run", response_model=PlanningContext)
    def run_workspace(workspace_id: int = Query(1)) -> PlanningContext:
        """Assemble and persist the whole workspace's merged planning context."""
        ctx = run_workspace_context(get_settings().rdb_dsn, workspace_id)
        if ctx is None:
            raise HTTPException(404, "no profiled datasets in this workspace yet")
        return ctx

    @router.get("/workspace", response_model=PlanningContext)
    def get_workspace_context(workspace_id: int = Query(1)) -> PlanningContext:
        """Fetch the latest workspace-wide planning context."""
        store = ContextStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(f"workspace_{workspace_id}")
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, "no workspace-wide planning context yet")
        return latest

    @router.get("/{dataset_id}", response_model=PlanningContext)
    def get_context(dataset_id: str,
                    workspace_id: int = Query(1)) -> PlanningContext:
        """Fetch the latest planning context for a dataset."""
        store = ContextStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, f"no planning context for dataset {dataset_id!r}")
        return latest

    return router
