"""Data Explorer API (v2) — the transparency surface over resolved entities.

Reads the relational source of truth (EntityStore) so every row carries its
golden-record attributes and the source records it traces back to. Pure shaping
lives in aryx.explore; this module is the thin HTTP wire.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks
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


class MaterializeHierarchyRequest(BaseModel):
    workspace_id: int = 1
    hub_attr: str | None = None
    label_attr: str | None = None
    parent_type: str | None = None
    child_type: str | None = None
    edge_name: str | None = None
    reproject: bool = True


def _store(workspace_id: int) -> EntityStore:
    return EntityStore(get_settings().rdb_dsn, workspace_id)


def _hierarchy_for(
    workspace_id: int, entities: list[tuple[int, str, dict]]
) -> tuple[str | None, str | None]:
    """Resolve the hub/label columns to group a workspace's entities by.

    Generalised (not workspace-specific): first honour the columns the user
    named in THIS workspace's goal (reusing ingest's column honouring, so the
    grouping matches what they asked for — e.g. parent_key, child_key);
    otherwise auto-detect a hub/spoke shape from the data. Returns (None, None)
    when neither applies, so the caller renders a flat view.
    """
    from aryx.api.file_ingest_api import _columns_in_context, _workspace_context

    attr_names = list({k for _, _, a in entities for k in (a or {})})
    named = _columns_in_context(
        _workspace_context(get_settings().rdb_dsn, workspace_id), attr_names)
    if named:
        return named[0], (named[1] if len(named) > 1 else None)
    return explore.detect_hierarchy(entities) or (None, None)


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
                 limit: int = 50, offset: int = 0, group: bool = False) -> dict:
        """Entities (optionally by type) with attributes + provenance.

        With ``group=true`` and a workspace that has a hub/spoke shape (named in
        the goal or auto-detected), returns rows grouped under their hub value
        (``offset`` = group offset). Otherwise a flat page (``offset`` = row
        offset). Grouping is opt-in so flat consumers (the Tree) are unaffected.
        """
        store = _store(workspace_id)
        try:
            all_entities = store.list_entities()
            prov = store.list_members_provenance()
            hub, label = _hierarchy_for(workspace_id, all_entities) if group \
                else (None, None)
            if hub:
                return explore.grouped_entities_view(
                    all_entities, prov, hub, label, ontology_type=type,
                    group_offset=offset)
            return explore.entities_view(
                all_entities, prov, ontology_type=type,
                limit=limit, offset=offset)
        except Exception as exc:  # noqa: BLE001
            logger.warning("data entities failed: %s", exc)
            return {"error": f"data unavailable: {exc}", "items": []}

    @router.get("/entity/{entity_id}")
    def entity(entity_id: int, workspace_id: int = 1) -> dict:
        """One entity's attributes, source records, and relationships."""
        store = _store(workspace_id)
        try:
            entities = store.list_entities()
            hub, label = _hierarchy_for(workspace_id, entities)
            detail = explore.entity_detail(
                entities, store.list_members_provenance(),
                store.list_relationships(), entity_id,
                hub_attr=hub, label_attr=label)
            return detail or {"error": "entity not found"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("data entity detail failed: %s", exc)
            return {"error": f"detail unavailable: {exc}"}

    @router.get("/graph")
    def graph(workspace_id: int = 1, level: str = "type") -> dict:
        """Knowledge map. level=type → aggregated shape; level=entity → per-entity."""
        store = _store(workspace_id)
        try:
            if level == "entity":
                entities = store.list_entities()
                hub, label = _hierarchy_for(workspace_id, entities)
                return explore.entity_graph_view(entities,
                                                 store.list_relationships(),
                                                 hub_attr=hub, label_attr=label)
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

    @router.post("/materialize-hierarchy")
    def materialize_hierarchy(req: MaterializeHierarchyRequest,
                              background_tasks: BackgroundTasks) -> dict:
        """Turn a detected hub/spoke display hierarchy into stored edges."""
        store = _store(req.workspace_id)
        try:
            entities = store.list_entities()
            hub, label = (
                (req.hub_attr, req.label_attr)
                if req.hub_attr else _hierarchy_for(req.workspace_id, entities)
            )
            if not hub:
                return {"error": "no hierarchy detected"}
            result = _materialize_hierarchy(
                store, entities, hub, label,
                parent_type=req.parent_type, child_type=req.child_type,
                edge_name=req.edge_name)
            projected = None
            if req.reproject:
                background_tasks.add_task(_reproject, req.workspace_id, store)
                projected = {"status": "queued"}
            return {**result, "projected": projected}
        except Exception as exc:  # noqa: BLE001
            logger.warning("data materialize hierarchy failed: %s", exc)
            return {"error": f"materialize failed: {exc}"}

    return router


def _reproject(workspace_id: int, store: EntityStore) -> dict:
    """Rebuild the FalkorDB projection so the graph reflects new edges."""
    from aryx.graph.falkor_store import FalkorStore
    from aryx.naming import ws_graph
    from aryx.project import project_graph

    falkor = FalkorStore(get_settings().graph_url, ws_graph(workspace_id))
    return project_graph(store, falkor, workspace_id=workspace_id)


def _materialize_hierarchy(
    store: EntityStore,
    entities: list[tuple[int, str, dict]],
    hub_attr: str,
    label_attr: str | None,
    parent_type: str | None = None,
    child_type: str | None = None,
    edge_name: str | None = None,
) -> dict:
    """Create real hub entities and hub->child relationships idempotently."""
    from collections import Counter

    from psycopg.types.json import Json

    from aryx.models import Relationship
    from aryx.queries import load
    from aryx.store.entity_store import _dumps

    candidates = [
        (eid, etype, attrs or {}) for eid, etype, attrs in entities
        if (attrs or {}).get(hub_attr) not in (None, "")
    ]
    if child_type:
        candidates = [row for row in candidates if row[1] == child_type]
    if not candidates:
        return {"hub_attr": hub_attr, "label_attr": label_attr,
                "created_hubs": 0, "created_edges": 0}
    child = child_type or Counter(etype for _, etype, _ in candidates).most_common(1)[0][0]
    candidates = [row for row in candidates if row[1] == child]
    parent = parent_type or explore._parent_type(child)
    rel_name = edge_name or f"HAS_{child.upper()}"

    by_hub: dict[str, int] = {}
    for eid, etype, attrs in entities:
        if etype != parent:
            continue
        hv = str((attrs or {}).get(hub_attr, "")).strip().lower()
        if hv:
            by_hub[hv] = eid

    existing = set(store.list_relationships())
    created_hubs = 0
    rels: list[Relationship] = []
    with store._pool.connection() as conn:  # noqa: SLF001 - scoped store helper
        with conn.cursor() as cur:
            for _eid, _etype, attrs in candidates:
                hv_raw = str(attrs.get(hub_attr, "")).strip()
                if not hv_raw:
                    continue
                key = hv_raw.lower()
                if key not in by_hub:
                    cur.execute(
                        load("insert_entity"),
                        (store._ws, parent,  # noqa: SLF001
                         Json({hub_attr: hv_raw, "name": hv_raw}, dumps=_dumps),
                         1.0),
                    )
                    row = cur.fetchone()
                    by_hub[key] = int(row[0]) if row else 0
                    created_hubs += 1
                hub_id = by_hub[key]
                if hub_id:
                    rel_tuple = (hub_id, _eid, rel_name)
                    if rel_tuple not in existing:
                        rels.append(Relationship(
                            source_entity_id=hub_id,
                            target_entity_id=_eid,
                            name=rel_name,
                            confidence=1.0,
                        ))
                        existing.add(rel_tuple)
    if rels:
        store.save_relationships(rels)
    return {
        "hub_attr": hub_attr,
        "label_attr": label_attr,
        "parent_type": parent,
        "child_type": child,
        "edge_name": rel_name,
        "created_hubs": created_hubs,
        "created_edges": len(rels),
    }
