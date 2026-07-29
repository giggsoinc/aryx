"""Deterministic Dataset Profiler API (C03).

GET  /profile/versions      — list recent profiles for a workspace.
GET  /profile/{dataset_id}  — latest profile for a dataset.
POST /profile/run           — (re)profile a dataset version on demand.

Profiles are normally produced automatically when a dataset is ingested
(see file_ingest_api._snapshot_dataset). These endpoints read them back and
allow an explicit re-profile.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.profiler.models import DatasetProfile
from aryx.profiler.run import run_profile
from aryx.store.profile_store import ProfileStore

logger = logging.getLogger(__name__)


class ProfileRunRequest(BaseModel):
    dataset_id: str
    dataset_version: str | None = None


def profile_router() -> APIRouter:
    """Build the Dataset Profiler router."""
    router = APIRouter(prefix="/profile")

    @router.post("/run", response_model=DatasetProfile)
    def run(req: ProfileRunRequest, workspace_id: int = Query(1)) -> DatasetProfile:
        """Profile a dataset version (defaults to latest) and persist it."""
        profile = run_profile(get_settings().rdb_dsn, workspace_id,
                              req.dataset_id, req.dataset_version)
        if profile is None:
            raise HTTPException(404, f"no snapshot for dataset {req.dataset_id!r}")
        return profile

    # Declared before /{dataset_id} so "versions" is not swallowed as an id.
    @router.get("/versions", response_model=list[DatasetProfile])
    def list_profiles(workspace_id: int = Query(1),
                      limit: int = Query(100, ge=1, le=500)) -> list[DatasetProfile]:
        """List recent profiles, newest first."""
        store = ProfileStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.get("/{dataset_id}", response_model=DatasetProfile)
    def get_profile(dataset_id: str,
                    workspace_id: int = Query(1)) -> DatasetProfile:
        """Fetch the latest profile for a dataset."""
        store = ProfileStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            raise HTTPException(404, f"no profile for dataset {dataset_id!r}")
        return latest

    return router
