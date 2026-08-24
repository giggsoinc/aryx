"""Adjudication API (G10): list pending pairs, record human decisions, stats.

Sits behind auth-warden's ApiKeyMiddleware like every other router. The
decide endpoint is the pattern G13 reuses for action approvals.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx import explore
from aryx.config import get_settings
from aryx.graph.falkor_store import FalkorStore
from aryx.pipeline.enrich import _build_type_ancestors
from aryx.project import project_graph
from aryx.resolution.review_queue import apply_decision
from aryx.resolution.survivorship import SurvivorshipPolicy
from aryx.store.adjudication_store import AdjudicationStore
from aryx.store.entity_store import EntityStore
from aryx.workspaces import WorkspaceStore, ws_graph

logger = logging.getLogger(__name__)


class DecideRequest(BaseModel):
    """Human verdict on one queued pair."""

    approve: bool
    decided_by: str


def _store(workspace_id: int) -> AdjudicationStore:
    """Build a workspace-scoped adjudication store."""
    return AdjudicationStore(get_settings().rdb_dsn, workspace_id)


def _load_policy(workspace_id: int) -> SurvivorshipPolicy:
    """The workspace's real, currently-configured survivorship policy."""
    wstore = WorkspaceStore(get_settings().rdb_dsn)
    try:
        return SurvivorshipPolicy.from_json(wstore.get_survivorship(workspace_id))
    finally:
        wstore.close()


def _reproject(workspace_id: int) -> dict[str, int]:
    """Rebuild the FalkorDB graph so an approved merge shows up immediately."""
    settings = get_settings()
    estore = EntityStore(settings.rdb_dsn, workspace_id)
    try:
        return project_graph(
            estore, FalkorStore(settings.graph_url, ws_graph(workspace_id)),
            type_ancestors=_build_type_ancestors(settings.rdb_dsn),
            workspace_id=workspace_id)
    finally:
        estore.close()


def _side_preview(store: AdjudicationStore, entities: list, provenance: list,
                  relationships: list, record_id: int) -> dict[str, Any]:
    """Human-readable view of one adjudication side.

    Prefers the resolved entity's golden-record attributes; falls back to
    the raw landed-record payload when the record hasn't been clustered
    into an entity yet (e.g. adjudication ran ahead of a later ingest pass).
    """
    entity_id = store.entity_of_record(record_id)
    if entity_id is not None:
        detail = explore.entity_detail(entities, provenance, relationships,
                                       entity_id)
        if detail:
            return {"record_id": record_id, "entity_id": entity_id, **detail}
    payload = store.raw_records([record_id]).get(record_id, {})
    return {"record_id": record_id, "entity_id": None,
            "name": None, "attributes": payload, "sources": [],
            "relationships": []}


def adjudication_router() -> APIRouter:
    """Routes for the human adjudication queue."""
    router = APIRouter(prefix="/adjudication")

    @router.get("")
    def list_queue(workspace_id: int = 1, status: str = "pending",
                   limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """One page of queue rows (default: pending, oldest first)."""
        return _store(workspace_id).page(status, min(limit, 200), offset)

    @router.get("/{adjudication_id}/preview")
    def preview(adjudication_id: int, workspace_id: int = 1) -> dict[str, Any]:
        """Human-readable view of both sides of a queued pair."""
        store = _store(workspace_id)
        row = store.get(adjudication_id)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"adjudication {adjudication_id} not found")
        estore = EntityStore(get_settings().rdb_dsn, workspace_id)
        entities = estore.list_entities()
        provenance = estore.list_members_provenance()
        relationships = estore.list_relationships()
        return {
            "id": row["id"], "score": row["score"],
            "llm_verdict": row["llm_verdict"], "llm_reason": row["llm_reason"],
            "status": row["status"],
            "left": _side_preview(store, entities, provenance, relationships,
                                  row["left_record_id"]),
            "right": _side_preview(store, entities, provenance, relationships,
                                   row["right_record_id"]),
        }

    @router.post("/{adjudication_id}/decide")
    def decide(adjudication_id: int, req: DecideRequest,
               workspace_id: int = 1) -> dict[str, Any]:
        """Record a human verdict; approval merges the affected entities
        under the workspace's real survivorship policy and re-projects the
        graph so the merge shows up immediately."""
        store = _store(workspace_id)
        try:
            result = apply_decision(store, adjudication_id, req.approve,
                                    req.decided_by, _load_policy(workspace_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if result.get("merged"):
            result["graph"] = _reproject(workspace_id)
        return result

    @router.get("/stats")
    def stats(workspace_id: int = 1) -> dict[str, Any]:
        """Pending count, approval rate, human/LLM agreement rate."""
        return _store(workspace_id).stats()

    return router
