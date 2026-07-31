"""Knowledge Graph Intake & Validation API (C05).

POST /graph-intake/run            — derive + validate + version the workspace graph.
GET  /graph-intake/versions       — list recent validated graph versions.
GET  /graph-intake/{graph_id}     — latest intake report for a graph.
GET  /graph-intake/{graph_id}/adapter — bounded read of the normalized graph.

Graphs are auto-derived from the workspace's Aryx entities/relationships and
validated deterministically before graph-based analysis is allowed.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from aryx.config import get_settings
from aryx.graph_intake.models import GraphIntakeResult
from aryx.graph_intake.run import run_intake
from aryx.store.graph_intake_store import GraphIntakeStore

logger = logging.getLogger(__name__)


def graph_intake_router() -> APIRouter:
    """Build the Knowledge Graph Intake router."""
    router = APIRouter(prefix="/graph-intake")

    @router.post("/run", response_model=GraphIntakeResult)
    def run(workspace_id: int = Query(1)) -> GraphIntakeResult:
        """Derive the workspace graph, validate it, and persist a version."""
        logger.info("graph-intake requested ws=%s", workspace_id)
        result = run_intake(get_settings().rdb_dsn, workspace_id)
        if result is None:
            logger.info("graph-intake found no entities ws=%s", workspace_id)
            raise HTTPException(404, "no entities in this workspace to build a graph")
        return result

    # Declared before /{graph_id} so "versions" is not swallowed as an id.
    @router.get("/versions", response_model=list[GraphIntakeResult])
    def list_versions(workspace_id: int = Query(1),
                      limit: int = Query(50, ge=1, le=500)) -> list[GraphIntakeResult]:
        """List recent validated graph versions, newest first."""
        store = GraphIntakeStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.get("/{graph_id}", response_model=GraphIntakeResult)
    def get_graph(graph_id: str, workspace_id: int = Query(1)) -> GraphIntakeResult:
        """Fetch the latest intake report for a graph."""
        store = GraphIntakeStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(graph_id)
        finally:
            store.close()
        if latest is None:
            logger.info("no graph intake found ws=%s graph=%s", workspace_id, graph_id)
            raise HTTPException(404, f"no graph {graph_id!r}")
        return latest

    @router.get("/{graph_id}/adapter")
    def adapter(graph_id: str, workspace_id: int = Query(1),
                limit: int = Query(100, ge=1, le=5000)) -> dict:
        """Bounded adapter read of the normalized graph (for the graph profiler)."""
        store = GraphIntakeStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.adapter_read(graph_id, limit)
        finally:
            store.close()

    return router
