"""AI ontology assist API (Slice W2 / option f).

Stateless: takes type_name + (optional) existing attrs + workspace context,
returns suggested attributes. The UI shows the suggestions, user picks
which ones to add, then saves through the normal POST /ontology/types.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from aryx.api.admin_api import _local_broker
from aryx.brief import serialize as serialize_brief
from aryx.config import get_settings
from aryx.ontology_assist import suggest_attrs
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)


class SuggestAttrsRequest(BaseModel):
    """Ask the model for additional attributes for one entity type."""

    workspace_id: int = 1
    type_name: str
    existing: list[str] = []


def ontology_assist_router() -> APIRouter:
    """Build the AI ontology assist router."""
    router = APIRouter(prefix="/ontology/assist")

    @router.post("/suggest-attrs")
    def suggest_attrs_endpoint(req: SuggestAttrsRequest) -> dict[str, Any]:
        """Return AI-proposed attribute names for an entity type."""
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            workspaces = store.list_all()
        finally:
            store.close()
        brief: dict[str, Any] = {}
        for w in workspaces:
            if int(w.get("id", 0)) == int(req.workspace_id):
                brief = w.get("brief") or {}
                break
        brief_text = serialize_brief(brief)
        result = suggest_attrs(_local_broker(), brief_text,
                                req.type_name, req.existing)
        logger.info("attrs suggested ws=%s type=%s n=%s",
                    req.workspace_id, req.type_name,
                    len(result["attributes"]))
        return result

    return router
