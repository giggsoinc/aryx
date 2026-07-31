"""Semantic Field Interpreter API (C04).

GET  /semantic/versions      — list recent semantic profiles for a workspace.
GET  /semantic/{dataset_id}  — latest semantic profile for a dataset.
POST /semantic/run           — (re)interpret a dataset version on demand.

Semantic profiles are normally produced automatically after profiling
(see file_ingest_api._snapshot_dataset). Columns are grounded against the
workspace ontology; uncertain columns are returned as unresolved_fields.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aryx.api.admin_api import _local_broker
from aryx.config import get_settings
from aryx.semantic.models import SemanticProfile
from aryx.semantic.run import run_interpret
from aryx.store.semantic_store import SemanticStore

logger = logging.getLogger(__name__)


class SemanticRunRequest(BaseModel):
    dataset_id: str
    dataset_version: str | None = None
    domain: str = ""


def semantic_router() -> APIRouter:
    """Build the Semantic Field Interpreter router."""
    router = APIRouter(prefix="/semantic")

    @router.post("/run", response_model=SemanticProfile)
    def run(req: SemanticRunRequest, workspace_id: int = Query(1)) -> SemanticProfile:
        """Interpret a dataset version (defaults to latest) and persist it."""
        logger.info("semantic run request ws=%s dataset=%s version=%s domain=%s",
                   workspace_id, req.dataset_id, req.dataset_version, req.domain)
        profile = run_interpret(
            get_settings().rdb_dsn, workspace_id, req.dataset_id,
            req.dataset_version, domain=req.domain, broker=_local_broker(),
        )
        if profile is None:
            logger.info("no profile found for dataset=%s ws=%s", req.dataset_id, workspace_id)
            raise HTTPException(404, f"no profile for dataset {req.dataset_id!r}")
        return profile

    # Declared before /{dataset_id} so "versions" is not swallowed as an id.
    @router.get("/versions", response_model=list[SemanticProfile])
    def list_profiles(workspace_id: int = Query(1),
                      limit: int = Query(100, ge=1, le=500)) -> list[SemanticProfile]:
        """List recent semantic profiles, newest first."""
        store = SemanticStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.get("/{dataset_id}", response_model=SemanticProfile)
    def get_semantic(dataset_id: str,
                     workspace_id: int = Query(1)) -> SemanticProfile:
        """Fetch the latest semantic profile for a dataset."""
        store = SemanticStore(get_settings().rdb_dsn, workspace_id)
        try:
            latest = store.latest(dataset_id)
        finally:
            store.close()
        if latest is None:
            logger.info("no semantic profile found for dataset=%s ws=%s", dataset_id, workspace_id)
            raise HTTPException(404, f"no semantic profile for dataset {dataset_id!r}")
        return latest

    return router
