"""Data Explorer API (v2) — the transparency surface over resolved entities.

Reads the relational source of truth (EntityStore) so every row carries its
golden-record attributes and the source records it traces back to. Pure shaping
lives in aryx.explore; this module is the thin HTTP wire.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from aryx import explore
from aryx.config import get_settings
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


def _store(workspace_id: int) -> EntityStore:
    return EntityStore(get_settings().rdb_dsn, workspace_id)


def data_router() -> APIRouter:
    router = APIRouter(prefix="/data")

    @router.get("/summary")
    def summary(workspace_id: int = 1) -> dict:
        """Type counts, source breakdown, and the dedup story."""
        store = _store(workspace_id)
        try:
            return explore.summarize(store.list_entities(),
                                     store.list_members_provenance())
        except Exception as exc:  # noqa: BLE001 — surface to the Data UI
            logger.warning("data summary failed: %s", exc)
            return {"error": f"data unavailable: {exc}"}

    @router.get("/entities")
    def entities(workspace_id: int = 1, type: str | None = None,
                 limit: int = 50, offset: int = 0) -> dict:
        """Entities (optionally by type) with attributes + provenance."""
        store = _store(workspace_id)
        try:
            return explore.entities_view(
                store.list_entities(), store.list_members_provenance(),
                ontology_type=type, limit=limit, offset=offset)
        except Exception as exc:  # noqa: BLE001
            logger.warning("data entities failed: %s", exc)
            return {"error": f"data unavailable: {exc}", "items": []}

    return router
