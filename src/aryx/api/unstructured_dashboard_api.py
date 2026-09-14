"""Unstructured-data dashboard section — document entity word cloud.

GET /dashboard-unstructured/exists     — does this workspace have any
                                          document-sourced data at all.
GET /dashboard-unstructured/word-cloud — top document-sourced entity
                                          mentions by frequency, plus a
                                          discovery timeline.
GET /dashboard-unstructured/excerpts   — sample verbatim quotes for one
                                          entity, fetched on demand (click),
                                          never polled eagerly — span text
                                          is verbose and this is per-entity,
                                          unlike the aggregate views above.

Deliberately outside the C07-C14 governed dashboard-spec pipeline (see
`store/unstructured_dashboard_store.py` docstring) — a plain frequency count,
never an LLM-drafted claim, so it carries no `source_ref` into a KPI/Analysis
and is rendered as its own independent section, not a DashboardModel
component.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.store.unstructured_dashboard_store import UnstructuredDashboardStore

logger = logging.getLogger(__name__)


class DocumentEntity(BaseModel):
    ontology_type: str
    name: str
    count: int


class HasDocumentsResponse(BaseModel):
    has_documents: bool


class TimelinePoint(BaseModel):
    date: str
    count: int


class WordCloudResponse(BaseModel):
    entities: list[DocumentEntity]
    timeline: list[TimelinePoint]


class ExcerptsResponse(BaseModel):
    excerpts: list[str]


def unstructured_dashboard_router() -> APIRouter:
    """Build the unstructured-dashboard router."""
    router = APIRouter(prefix="/dashboard-unstructured")

    @router.get("/exists", response_model=HasDocumentsResponse)
    def exists(workspace_id: int = Query(1)) -> HasDocumentsResponse:
        """Whether this workspace has any document-sourced landed data."""
        store = UnstructuredDashboardStore(get_settings().rdb_dsn, workspace_id)
        try:
            return HasDocumentsResponse(has_documents=store.has_document_data())
        finally:
            store.close()

    @router.get("/word-cloud", response_model=WordCloudResponse)
    def word_cloud(
        workspace_id: int = Query(1),
        limit: int = Query(40, ge=1, le=200),
        min_count: int = Query(2, ge=1, le=100),
    ) -> WordCloudResponse:
        """Top document-sourced entity mentions by frequency, plus a
        day-by-day discovery timeline — one fetch backs the word cloud, the
        entity-type/top-entity charts, and the timeline chart together,
        since the frontend already polls this workspace's document data on
        one cycle."""
        store = UnstructuredDashboardStore(get_settings().rdb_dsn, workspace_id)
        try:
            entity_rows = store.top_document_entities(limit=limit, min_count=min_count)
            timeline_rows = store.entity_timeline()
        finally:
            store.close()
        logger.info("word-cloud entities ws=%s count=%d timeline_points=%d",
                   workspace_id, len(entity_rows), len(timeline_rows))
        return WordCloudResponse(
            entities=[DocumentEntity(**r) for r in entity_rows],
            timeline=[TimelinePoint(**r) for r in timeline_rows],
        )

    @router.get("/excerpts", response_model=ExcerptsResponse)
    def excerpts(
        workspace_id: int = Query(1),
        ontology_type: str = Query(...),
        name: str = Query(...),
        limit: int = Query(3, ge=1, le=10),
    ) -> ExcerptsResponse:
        """Sample verbatim excerpts for one entity — fetched on click, never
        part of the eager word-cloud poll (see module docstring)."""
        store = UnstructuredDashboardStore(get_settings().rdb_dsn, workspace_id)
        try:
            rows = store.entity_excerpts(ontology_type, name, limit=limit)
        finally:
            store.close()
        logger.info("excerpts ws=%s type=%s name=%s count=%d",
                   workspace_id, ontology_type, name, len(rows))
        return ExcerptsResponse(excerpts=rows)

    return router
