"""Brief drafting API — turn a seed sentence + optional doc text into a brief.

Stateless: it drafts and returns the 5-field brief; the UI lets the user
edit it, then persists via the existing workspace brief PATCH. Document
text is extracted client-side (UI) and posted as plain text here.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from aryx.api.admin_api import _local_broker
from aryx.brief_draft import draft_from_text

logger = logging.getLogger(__name__)


class DraftBriefRequest(BaseModel):
    """Seed sentence and/or extracted document text to draft a brief from."""

    seed: str = ""
    doc_text: str = ""
    workspace_id: int = 1


def brief_router() -> APIRouter:
    """Build the /admin/workspaces brief-drafting router."""
    router = APIRouter(prefix="/admin/workspaces")

    @router.post("/{workspace_id}/draft-brief")
    def draft_brief(workspace_id: int,
                    req: DraftBriefRequest) -> dict[str, Any]:
        """Draft a 5-field brief from a seed sentence and/or document text."""
        brief = draft_from_text(_local_broker(), req.seed, req.doc_text)
        logger.info("brief drafted ws=%s seed=%d doc=%d", workspace_id,
                    len(req.seed), len(req.doc_text))
        return {"workspace_id": workspace_id, "brief": brief}

    return router
