"""Ontology versions + change-log API — snapshot, list, browse changes."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from aryx.api.ontology_browse import list_browse
from aryx.config import get_settings
from aryx.store.rule_store import RuleStore
from aryx.store.version_store import VersionStore

logger = logging.getLogger(__name__)


class SnapshotRequest(BaseModel):
    """Create a new ontology version snapshot."""

    workspace_id: int = 1
    label: str = ""
    actor: str = "user"


def versions_router() -> APIRouter:
    """Build the /ontology-versions router."""
    router = APIRouter(prefix="/ontology-versions")

    @router.post("")
    def snapshot(req: SnapshotRequest) -> dict[str, Any]:
        """Create a new version snapshot of current types + rules."""
        dsn = get_settings().rdb_dsn
        rules = RuleStore(dsn)
        vs = VersionStore(dsn)
        try:
            types = list_browse(req.workspace_id).get("types", []) or []
            rule_rows = rules.list_(req.workspace_id)
            return vs.snapshot(req.workspace_id, req.label, types,
                               rule_rows, req.actor)
        finally:
            rules.close()
            vs.close()

    @router.get("")
    def list_versions(workspace_id: int = 1,
                      limit: int = 25) -> list[dict[str, Any]]:
        """Recent version snapshots, newest first."""
        vs = VersionStore(get_settings().rdb_dsn)
        try:
            return vs.list_(workspace_id, limit)
        finally:
            vs.close()

    @router.get("/changes")
    def changes(workspace_id: int = 1,
                limit: int = 50) -> list[dict[str, Any]]:
        """Recent ontology change-log rows."""
        vs = VersionStore(get_settings().rdb_dsn)
        try:
            return vs.changes(workspace_id, limit)
        finally:
            vs.close()

    return router
