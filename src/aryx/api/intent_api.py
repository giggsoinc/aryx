"""User Intent Capture API (C01).

POST /intent/capture      — validate + version a request, persist it, return it.
GET  /intent/captures     — list recent captures for a workspace.
GET  /intent/{request_id} — fetch one capture by correlation id.

Deterministic (no LLM). Capture always returns 200 with a UserIntent; callers
gate on `validation_status` ("invalid" means blocked, with field-level `errors`).
Every attempt (valid or invalid) is persisted for audit.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from aryx.config import get_settings
from aryx.intent.capture import capture_intent
from aryx.intent.models import UserIntent, UserIntentRequest
from aryx.pipeline.downstream import run_downstream
from aryx.store.dataset_store import DatasetStore
from aryx.store.intent_store import IntentStore

logger = logging.getLogger(__name__)


def intent_router() -> APIRouter:
    """Build the User Intent Capture router."""
    router = APIRouter(prefix="/intent")

    @router.post("/capture", response_model=UserIntent)
    def capture(request: UserIntentRequest, background_tasks: BackgroundTasks,
                workspace_id: int = Query(1)) -> UserIntent:
        """Validate, normalize, version, and persist a capture request.

        Once intent turns valid, backfills C03-C07 for every dataset already
        sitting in the workspace — those steps were deferred at ingest time
        until intent existed (see aryx.pipeline.downstream).
        """
        result = capture_intent(request)
        dsn = get_settings().rdb_dsn
        store = IntentStore(dsn, workspace_id)
        try:
            store.save(result)
        finally:
            store.close()
        logger.info(
            "intent/capture ws=%s request_id=%s status=%s warnings=%d errors=%d",
            workspace_id, result.request_id, result.validation_status,
            len(result.warnings), len(result.errors),
        )
        if result.validation_status == "valid":
            dstore = DatasetStore(dsn, workspace_id)
            try:
                dataset_ids = sorted({v.dataset_id for v in dstore.list_versions(500)})
            finally:
                dstore.close()
            if dataset_ids:
                logger.info(
                    "intent valid ws=%s; backfilling C03-C07 for %d dataset(s)",
                    workspace_id, len(dataset_ids),
                )
                background_tasks.add_task(run_downstream, dsn, workspace_id, dataset_ids)
        return result

    # Declared before /{request_id} so "captures" is not swallowed as an id.
    @router.get("/captures", response_model=list[UserIntent])
    def list_captures(workspace_id: int = Query(1),
                      limit: int = Query(50, ge=1, le=500)) -> list[UserIntent]:
        """List recent captures for a workspace, newest first."""
        store = IntentStore(get_settings().rdb_dsn, workspace_id)
        try:
            return store.list(limit)
        finally:
            store.close()

    @router.get("/{request_id}", response_model=UserIntent)
    def get_capture(request_id: str,
                    workspace_id: int = Query(1)) -> UserIntent:
        """Fetch one capture by correlation id."""
        store = IntentStore(get_settings().rdb_dsn, workspace_id)
        try:
            found = store.get(request_id)
        finally:
            store.close()
        if found is None:
            raise HTTPException(404, f"no capture with request_id {request_id!r}")
        return found

    return router
