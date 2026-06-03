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
