"""Dataset Upload & Ingestion API (C02) — read surface.

GET /dataset/versions     — list recent dataset versions for a workspace.
GET /dataset/{dataset_id} — fetch the latest version of a dataset.

Datasets are created during onboarding upload (see file_ingest_api._run_files,
which calls dataset.register_dataset to store an immutable, versioned snapshot).
This module only exposes the resulting records; there is no separate upload here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from aryx.config import get_settings
from aryx.dataset.models import DatasetIngestResult
from aryx.store.dataset_store import DatasetStore

logger = logging.getLogger(__name__)


def dataset_router() -> APIRouter:
    """Build the Dataset read router."""
    router = APIRouter(prefix="/dataset")

    # Declared before /{dataset_id} so "versions" is not swallowed as an id.
    @router.get("/versions", response_model=list[DatasetIngestResult])
    def list_versions(workspace_id: int = Query(1),
                      limit: int = Query(50, ge=1, le=500)) -> list[DatasetIngestResult]:
        """List recent dataset versions, newest first."""
        store = DatasetStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list_versions(limit)
        finally:
            store.close()

    @router.get("/{dataset_id}", response_model=DatasetIngestResult)
    def get_dataset(dataset_id: str,
                    workspace_id: int = Query(1)) -> DatasetIngestResult:
        """Fetch the latest version of a dataset."""
        store = DatasetStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, f"no dataset {dataset_id!r}")
        return latest

    return router
