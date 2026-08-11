"""Explicit post-ingest entity-linking API.

Exposes the existing `link_entities()` pipeline step (previously only ever
called internally, at ingest time, with auto-inferred FK specs — see
file_ingest_api.py) so a user can draw a REAL, data-level foreign-key link
between two already-ingested entity types from the Model tab. This is
distinct from POST /ontology/relationships, which only records a cosmetic
diagram edge (no source_attr/target_attr) with no effect on the actual
knowledge graph or graph_relation charts.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from aryx.config import get_settings
from aryx.pipeline.orchestrate import link_entities

logger = logging.getLogger(__name__)


class FkLinkSpec(BaseModel):
    """One (source_type, source_attr) -[name]-> (target_type, target_attr)
    exact-value-match foreign-key link — see orchestrate.link_by_attribute."""

    source_type: str
    source_attr: str
    target_type: str
    target_attr: str
    name: str


class LinkEntitiesRequest(BaseModel):
    fk_links: list[FkLinkSpec] = Field(default_factory=list)


def pipeline_link_router() -> APIRouter:
    """Build the explicit entity-linking router."""
    router = APIRouter(prefix="/pipeline")

    @router.post("/link-entities")
    def create_links(req: LinkEntitiesRequest, workspace_id: int = Query(1)) -> dict:
        """Materialize real FK edges across already-resolved entities and
        re-project the graph. `relationships` in the response is the exact
        count of edges actually created — 0 means the two attributes never
        matched on any real value; the caller must surface that as a real
        outcome, never treat a 0-count call as a silent success."""
        settings = get_settings()
        fk_links = [spec.model_dump() for spec in req.fk_links]
        logger.info("explicit link-entities ws=%s links=%d", workspace_id, len(fk_links))
        counts = link_entities(settings.rdb_dsn, settings.graph_url, workspace_id, fk_links)
        if not fk_links:
            logger.warning("link-entities called with zero fk_links ws=%s", workspace_id)
        return counts

    return router
