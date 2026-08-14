"""Knowledge Graph Profiler API (C06).

POST /graph-profile/run           — profile the workspace's validated graph.
GET  /graph-profile/versions      — list recent graph profiles.
GET  /graph-profile/{graph_id}    — latest graph profile for a graph.

Profiles are produced automatically after graph intake (C05). Every verified
path is backed by real relationships — none are invented.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.graph_profiler.models import GraphProfile
from aryx.graph_profiler.run import run_graph_profile
from aryx.store.graph_profile_store import GraphProfileStore

logger = logging.getLogger(__name__)


class GraphProfileRunRequest(BaseModel):
    graph_id: str | None = None
    user_objective: str | None = None
    maximum_path_depth: int = 3


def graph_profile_router() -> APIRouter:
    """Build the Knowledge Graph Profiler router."""
    router = APIRouter(prefix="/graph-profile")

    @router.post("/run", response_model=GraphProfile)
    def run(req: GraphProfileRunRequest, workspace_id: int = Query(1)) -> GraphProfile:
        """Profile the latest validated graph and persist the profile."""
        logger.info("graph-profile requested ws=%s graph=%s depth=%d",
                   workspace_id, req.graph_id, req.maximum_path_depth)
        prof = run_graph_profile(
            get_settings().rdb_dsn, workspace_id, req.graph_id,
            user_objective=req.user_objective, max_depth=req.maximum_path_depth,
        )
        if prof is None:
            logger.info("graph-profile found no validated graph ws=%s graph=%s",
                       workspace_id, req.graph_id)
            raise HTTPException(404, "no validated graph to profile; run graph intake first")
        return prof

    # Declared before /{graph_id} so "versions" is not swallowed as an id.
    @router.get("/versions", response_model=list[GraphProfile])
    def list_profiles(workspace_id: int = Query(1),
                      limit: int = Query(50, ge=1, le=500)) -> list[GraphProfile]:
        """List recent graph profiles, newest first."""
        store = GraphProfileStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.get("/{graph_id}", response_model=GraphProfile)
    def get_profile(graph_id: str, workspace_id: int = Query(1)) -> GraphProfile:
        """Fetch the latest profile for a graph."""
        store = GraphProfileStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(graph_id)
        finally:
            store.close()
        if latest is None:
            logger.info("no graph profile found ws=%s graph=%s", workspace_id, graph_id)
            raise HTTPException(404, f"no graph profile for {graph_id!r}")
        return latest

    return router
