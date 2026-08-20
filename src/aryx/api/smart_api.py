"""Brief-led smart understand API — customer brief + samples → graph plan.

Architecture note (restored from v1.5.3): the customer authors the brief
BEFORE upload. Nothing in this module may overwrite `aryx_workspace.brief`
while that brief is populated — the model's reading of the data lands in
`aryx_workspace.data_understanding` and is surfaced read-only.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from aryx import understanding
from aryx.config import get_settings
from aryx.pipeline.smart_understand import sample_bytes, understand_samples
from aryx.store.migrate import apply_migrations
from aryx.workspaces import WorkspaceStore

logger = logging.getLogger(__name__)
_MAX_FILE = 20 * 1024 * 1024
_MAX_FILES = 20

# In-process plan cache (same process as API). Keyed by plan_id.
_PLANS: dict[str, dict[str, Any]] = {}


class ApplyRequest(BaseModel):
    workspace_id: int = 1
    brief: dict[str, Any] = Field(default_factory=dict)
    graph_plan: dict[str, Any] = Field(default_factory=dict)
    plan_id: str | None = None


def smart_router() -> APIRouter:
    router = APIRouter(prefix="/admin/smart")

    @router.post("/understand")
    async def understand(
        files: list[UploadFile] = File(...),
        user_hint: str = Form(""),
        workspace_id: int = Form(1),
    ) -> dict[str, Any]:
        """Sample uploaded files and draft brief + graph plan (no full ingest)."""
        if not files:
            raise HTTPException(400, "at least one file required")
        if len(files) > _MAX_FILES:
            raise HTTPException(400, f"max {_MAX_FILES} files for understand")
        samples: list[dict[str, Any]] = []
        for f in files:
            data = await f.read()
            if len(data) > _MAX_FILE:
                raise HTTPException(400, f"{f.filename}: exceeds 20 MB")
            samples.append(sample_bytes(data, f.filename or "upload"))
        apply_migrations(get_settings().rdb_dsn)
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            brief = understanding.customer_brief(store, workspace_id)
        finally:
            store.close()
        result = understand_samples(samples, user_hint=user_hint,
                                    customer_brief=brief)
        plan_id = uuid.uuid4().hex
        _PLANS[plan_id] = {
            "workspace_id": workspace_id,
            "result": result,
            "filenames": [s["filename"] for s in samples],
        }
        result = {**result, "plan_id": plan_id, "workspace_id": workspace_id}
        return result

    @router.post("/apply")
    def apply(req: ApplyRequest) -> dict[str, Any]:
        """Persist the DERIVED reading of the data + the graph plan.

        The customer brief is authoritative and is never overwritten here —
        see `aryx.understanding` for the one soft-gate exception.
        """
        apply_migrations(get_settings().rdb_dsn)
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            cached = (_PLANS.get(req.plan_id or "") or {})
            result = cached.get("result") or {}
            plan = req.graph_plan or result.get("graph_plan") or {}
            outcome = understanding.record(
                store, req.workspace_id, req.brief or {}, plan, result,
                cached.get("filenames") or [])
            if plan:
                understanding.stash_plan_context(
                    store, req.workspace_id, outcome["brief"], plan)
            return {
                "status": "ok",
                "workspace_id": req.workspace_id,
                "brief": outcome["brief"],
                "brief_source": outcome["brief_source"],
                "data_understanding": understanding.normalize_lists(
                    req.brief or {}),
                "graph_plan": plan,
            }
        finally:
            store.close()

    @router.get("/plan/{plan_id}")
    def get_plan(plan_id: str) -> dict[str, Any]:
        hit = _PLANS.get(plan_id)
        if not hit:
            raise HTTPException(404, "unknown or expired plan")
        return hit["result"]

    return router
