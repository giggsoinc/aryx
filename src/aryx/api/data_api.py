"""Data Explorer API (v2) — the transparency surface over resolved entities.

Reads the relational source of truth (EntityStore) so every row carries its
golden-record attributes and the source records it traces back to. Pure shaping
lives in aryx.explore; this module is the thin HTTP wire.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from aryx import explore
from aryx.config import get_settings
from aryx.store.entity_store import EntityStore

logger = logging.getLogger(__name__)


class FkLink(BaseModel):
    source_type: str
    source_attr: str
    target_type: str
    target_attr: str
    name: str


class RelateRequest(BaseModel):
    workspace_id: int = 1
    links: list[FkLink] = []
    replace: bool = True
    reproject: bool = True


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

    @router.get("/graph")
    def graph(workspace_id: int = 1, level: str = "type") -> dict:
        """Knowledge map. level=type → aggregated shape; level=entity → per-entity."""
        store = _store(workspace_id)
        try:
            if level == "entity":
                return explore.entity_graph_view(store.list_entities(),
                                                 store.list_relationships())
            return explore.graph_view(store.list_entities(),
                                      store.list_relationships())
        except Exception as exc:  # noqa: BLE001
            logger.warning("data graph failed: %s", exc)
            return {"error": f"graph unavailable: {exc}",
                    "type_nodes": [], "type_edges": [], "nodes": [], "edges": []}

    @router.post("/relate")
    def relate(req: RelateRequest) -> dict:
        """Derive relationships from foreign-key attribute links, then reproject.

        Each link creates edges where source_type.source_attr ==
        target_type.target_attr (exact, no LLM). Idempotent with replace=True.
        """
        from aryx.pipeline.fk_edges import link_by_attribute

        store = _store(req.workspace_id)
        try:
            cleared = store.clear_relationships() if req.replace else 0
            created = 0
            per_link = []
            for link in req.links:
                n = link_by_attribute(store, link.source_type, link.source_attr,
                                      link.target_type, link.target_attr, link.name)
                per_link.append({"name": link.name, "created": n})
                created += n
            projected = _reproject(req.workspace_id, store) if req.reproject else None
            return {"cleared": cleared, "created": created,
                    "per_link": per_link, "projected": projected}
        except Exception as exc:  # noqa: BLE001
            logger.warning("data relate failed: %s", exc)
            return {"error": f"relate failed: {exc}"}

    return router


def _reproject(workspace_id: int, store: EntityStore) -> dict:
    """Rebuild the FalkorDB projection so the graph reflects new edges."""
    from aryx.graph.falkor_store import FalkorStore
    from aryx.naming import ws_graph
    from aryx.project import project_graph

    falkor = FalkorStore(get_settings().graph_url, ws_graph(workspace_id))
    return project_graph(store, falkor, workspace_id=workspace_id)
