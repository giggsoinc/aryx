"""Data-first smart understand API — sample files → brief + graph plan."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

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
        result = understand_samples(samples, user_hint=user_hint)
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
        """Persist drafted brief (and graph_plan) on the workspace."""
        apply_migrations(get_settings().rdb_dsn)
        store = WorkspaceStore(get_settings().rdb_dsn)
        try:
            brief = req.brief or {}
            # Normalize list fields
            for key in ("objectives", "roles", "questions"):
                v = brief.get(key)
                if isinstance(v, str):
                    brief[key] = [ln.strip() for ln in v.splitlines() if ln.strip()]
            ws = store.set_brief(req.workspace_id, brief)
            # Stash graph_plan inside brief meta-ish: store on workspace context
            # if API supports it; also return for client to pass into ingest.
            plan = req.graph_plan
            if req.plan_id and req.plan_id in _PLANS:
                cached = _PLANS[req.plan_id]["result"].get("graph_plan") or {}
                if not plan:
                    plan = cached
            if plan:
                try:
                    # Append plan summary into context for extractors.
                    ctx_bits = []
                    b = brief
                    if b.get("domain"):
                        ctx_bits.append(f"Domain: {b['domain']}")
                    outcomes = (plan.get("outcomes") or [])[:6]
                    if outcomes:
                        ctx_bits.append("Graph outcomes: " + "; ".join(
                            str(o) for o in outcomes))
                    prim = plan.get("primary_types") or []
                    dims = plan.get("dimension_types") or []
                    names = [p.get("name") for p in prim if isinstance(p, dict)]
                    names += [d.get("name") for d in dims if isinstance(d, dict)]
                    if names:
                        ctx_bits.append(
                            "Planned entity types: " + ", ".join(str(n) for n in names))
                    if ctx_bits:
                        store.set_context(req.workspace_id, "\n".join(ctx_bits))
                except Exception:  # noqa: BLE001
                    logger.debug("context stash skipped", exc_info=True)
            return {
                "status": "ok",
                "workspace": ws,
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
