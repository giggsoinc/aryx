"""Derive-a-new-type-by-dedup API.

Exposes derive_entities_by_column() so a user can turn an already-resolved
type's column (e.g. ContractLineItem."Customer Number") into a real,
populated entity type (Customer) from the Model tab — a prerequisite for
/pipeline/link-entities to then draw real FK edges to it.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from aryx.config import get_settings
from aryx.pipeline.derive_entities import derive_entities_by_column

logger = logging.getLogger(__name__)


class DeriveEntitiesRequest(BaseModel):
    """Dedupe source_type by group_by_attr into a new populated type."""

    source_type: str
    group_by_attr: str
    new_type_name: str
    carry_attrs: list[str] = Field(default_factory=list)


def pipeline_derive_router() -> APIRouter:
    """Build the derive-entities router."""
    router = APIRouter(prefix="/pipeline")

    @router.post("/derive-entities")
    def derive(req: DeriveEntitiesRequest, workspace_id: int = Query(1)) -> dict:
        """Materialize a new entity type by deduplicating an existing
        type's attribute. `created` in the response is the exact count of
        new entities written — 0 means no source entity had group_by_attr;
        the caller must surface that as a real outcome, never a silent
        success."""
        settings = get_settings()
        logger.info("derive-entities ws=%s source=%s group_by=%s new_type=%s",
                    workspace_id, req.source_type, req.group_by_attr, req.new_type_name)
        counts = derive_entities_by_column(
            settings.rdb_dsn, settings.graph_url, workspace_id,
            req.source_type, req.group_by_attr, req.new_type_name, req.carry_attrs,
        )
        if counts.get("created", 0) == 0:
            logger.warning("derive-entities created 0 entities ws=%s source=%s group_by=%s",
                            workspace_id, req.source_type, req.group_by_attr)
        return counts

    return router
