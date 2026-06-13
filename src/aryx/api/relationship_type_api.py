"""Declared relationship types API (Slice W2 / option g).

REST shell over RelationshipTypeStore. The modelling canvas (apps/web/model)
POSTs here when the user draws an edge; GET returns the same set so a
canvas reload shows the drawn relationships back.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.store.relationship_type_store import RelationshipTypeStore

logger = logging.getLogger(__name__)


class RelationshipTypeRequest(BaseModel):
    """Declare a (source -[name]-> target) relationship type."""

    workspace_id: int = 1
    name: str
    source_type: str
    target_type: str
    description: str = ""


def relationship_type_router() -> APIRouter:
    """Build the declared-relationship-types router."""
    router = APIRouter(prefix="/ontology/relationships")

    @router.get("")
    def list_relationship_types(workspace_id: int = 1) -> list[dict[str, Any]]:
        """List declared relationship types for a workspace."""
        return RelationshipTypeStore(get_settings().rdb_dsn).list(workspace_id)

    @router.post("")
    def upsert_relationship_type(
        req: RelationshipTypeRequest,
    ) -> dict[str, Any]:
        """Idempotent declare; safe to call from the canvas on every edge."""
        try:
            return RelationshipTypeStore(get_settings().rdb_dsn).upsert(
                req.workspace_id, req.name, req.source_type,
                req.target_type, req.description)
        except Exception as exc:
            raise HTTPException(400, f"upsert failed: {exc}") from exc

    @router.delete("/{rel_id}")
    def delete_relationship_type(rel_id: int) -> dict[str, Any]:
        """Hard-delete a declared relationship type."""
        RelationshipTypeStore(get_settings().rdb_dsn).delete(rel_id)
        return {"status": "deleted", "id": rel_id}

    return router
