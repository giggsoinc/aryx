"""Workspace management API: create / list / delete isolated spaces."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.graph import FalkorStore
from aryx.store.migrate import apply_migrations
from aryx.workspaces import WorkspaceStore, ws_graph

logger = logging.getLogger(__name__)


class WorkspaceRequest(BaseModel):
    name: str
    description: str = ""
    context: str = ""


class ContextRequest(BaseModel):
    context: str = ""


class BriefRequest(BaseModel):
    """Knowledge-modelling brief — 5 METHONTOLOGY-style competency questions."""

    domain: str = ""
    aim: str = ""
    objectives: list[str] = []
    scope: str = ""
    roles: list[str] = []


def workspace_router() -> APIRouter:
    router = APIRouter(prefix="/admin/workspaces")

    @router.get("")
    def list_workspaces() -> list[dict[str, Any]]:
        apply_migrations(get_settings().rdb_dsn)
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            return store.list_all()
        finally:
            store.close()

    @router.post("")
    def create_workspace(req: WorkspaceRequest) -> dict[str, Any]:
        apply_migrations(get_settings().rdb_dsn)
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            return store.create(req.name, req.description, req.context)
        except Exception as exc:  # noqa: BLE001 — duplicate name, etc.
            raise HTTPException(400, f"could not create workspace: {exc}") from exc
        finally:
            store.close()

    @router.patch("/{workspace_id}/context")
    def set_context(workspace_id: int, req: ContextRequest) -> dict[str, Any]:
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            return store.set_context(workspace_id, req.context)
        finally:
            store.close()

    @router.get("/{workspace_id}/survivorship")
    def get_survivorship(workspace_id: int) -> dict[str, Any]:
        """Return the workspace survivorship policy (G3)."""
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            return {"workspace_id": workspace_id,
                    "survivorship": store.get_survivorship(workspace_id)}
        finally:
            store.close()

    @router.put("/{workspace_id}/survivorship")
    def set_survivorship(workspace_id: int,
                         policy: dict[str, Any]) -> dict[str, Any]:
        """Replace the workspace survivorship policy (G3, skill hook)."""
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            return store.set_survivorship(workspace_id, policy)
        finally:
            store.close()

    @router.patch("/{workspace_id}/brief")
    def set_brief(workspace_id: int, req: BriefRequest) -> dict[str, Any]:
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            return store.set_brief(workspace_id, req.model_dump())
        finally:
            store.close()

    @router.post("/nuke")
    def nuke_system() -> dict[str, Any]:
        """Factory reset: truncate all data, drop non-Default workspaces."""
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            result = store.nuke()
        finally:
            store.close()
        for wid in (1, 2, 3):
            try:
                g = FalkorStore(get_settings().graph_url, ws_graph(wid))
                g.clear()
            except Exception:  # noqa: BLE001
                pass
        return result

    @router.post("/{workspace_id}/purge")
    def purge_workspace(workspace_id: int) -> dict[str, Any]:
        """Delete all data in a workspace but keep the workspace itself."""
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            result = store.purge_data(workspace_id)
        finally:
            store.close()
        try:
            FalkorStore(get_settings().graph_url,
                        ws_graph(workspace_id)).clear()
        except Exception:  # noqa: BLE001
            logger.debug("graph clear skipped ws=%s", workspace_id)
        return result

    @router.delete("/{workspace_id}")
    def delete_workspace(workspace_id: int) -> dict[str, Any]:
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            store.delete(workspace_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            store.close()
        try:
            FalkorStore(get_settings().graph_url, ws_graph(workspace_id)).clear()
        except Exception:  # noqa: BLE001 — graph may not exist yet
            logger.debug("graph drop skipped ws=%s", workspace_id)
        return {"status": "deleted", "workspace_id": workspace_id}

    return router
