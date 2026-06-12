"""Adjudication API (G10): list pending pairs, record human decisions, stats.

Sits behind auth-warden's ApiKeyMiddleware like every other router. The
decide endpoint is the pattern G13 reuses for action approvals.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.resolution.review_queue import apply_decision
from aryx.store.adjudication_store import AdjudicationStore

logger = logging.getLogger(__name__)


class DecideRequest(BaseModel):
    """Human verdict on one queued pair."""

    approve: bool
    decided_by: str


def _store(workspace_id: int) -> AdjudicationStore:
    """Build a workspace-scoped adjudication store."""
    return AdjudicationStore(get_settings().rdb_dsn, workspace_id)


def adjudication_router() -> APIRouter:
    """Routes for the human adjudication queue."""
    router = APIRouter(prefix="/adjudication")

    @router.get("")
    def list_queue(workspace_id: int = 1, status: str = "pending",
                   limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """One page of queue rows (default: pending, oldest first)."""
        return _store(workspace_id).page(status, min(limit, 200), offset)

    @router.post("/{adjudication_id}/decide")
    def decide(adjudication_id: int, req: DecideRequest,
               workspace_id: int = 1) -> dict[str, Any]:
        """Record a human verdict; approval merges the affected entities."""
        store = _store(workspace_id)
        try:
            return apply_decision(store, adjudication_id, req.approve,
                                  req.decided_by)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/stats")
    def stats(workspace_id: int = 1) -> dict[str, Any]:
        """Pending count, approval rate, human/LLM agreement rate."""
        return _store(workspace_id).stats()

    return router
