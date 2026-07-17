"""Document self-discovery API: read → summary → confirm (no ontology input).

The user just uploads files. Reading discovers entity types from content; the
summary is reviewed; confirm ingests only the approved types. Reading and
ingesting both run as durable jobs so the UI can show live progress.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from aryx import discoveries
from aryx.api.admin_api import _local_broker
from aryx.config import get_settings
from aryx.pipeline.doc_discovery import DATA_EXTS, DOC_EXTS, ingest_confirmed, read_files
from aryx.store.job_store import JobStore
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)
_MAX_FILE = 20 * 1024 * 1024


class ConfirmRequest(BaseModel):
    discovery_id: str
    approved_types: list[str] = []
    approved_files: list[str] = []


def _save_tmp(data: bytes, suffix: str) -> Path:
    tmp = NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


def _read_job(items: list[tuple[bytes, str]], context: str, did: str,
              workspace_id: int = 1) -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    try:
        jobs.update_stage(did, "Reading", 30, f"Reading {len(items)} file(s)…")
        doc_paths = [_save_tmp(d, Path(n).suffix) for d, n in items
                     if Path(n).suffix.lower() in DOC_EXTS]
        tabular = [(d, n) for d, n in items if Path(n).suffix.lower() in DATA_EXTS]
        result = read_files(doc_paths, tabular, _local_broker(), context)
        result["workspace_id"] = workspace_id
        discoveries.put(did, result)
        jobs.finish(did, run_id=None, status="complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("doc read failed did=%s: %s", did, exc)
        jobs.finish(did, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def _confirm_job(did: str, types: list[str], files: list[str], job_id: str) -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    data = discoveries.get(did)
    try:
        if not data:
            raise ValueError("discovery expired — re-read the files")
        ingest_confirmed(data, types, files, _local_broker(), jobs, job_id,
                         data.get("workspace_id", 1))
        jobs.finish(job_id, run_id=None, status="complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("doc confirm failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def doc_discover_router() -> APIRouter:
    router = APIRouter(prefix="/admin/docs")

    @router.post("/read")
    async def read(background_tasks: BackgroundTasks,
                   files: list[UploadFile] = File(...), context: str = Form(""),
                   workspace_id: int = Form(1)) -> dict[str, Any]:
        settings = get_settings()
        apply_migrations(settings.rdb_dsn)
        items: list[tuple[bytes, str]] = []
        for f in files:
            data = await f.read()
            if len(data) > _MAX_FILE:
                raise HTTPException(400, f"{f.filename}: exceeds 20 MB")
            items.append((data, f.filename or "upload"))
        did = uuid.uuid4().hex
        jobs = JobStore(settings.rdb_dsn)
        try:
            jobs.create(did, "discovery", f"{len(items)} file(s)", workspace_id)
        finally:
            jobs.close()
        background_tasks.add_task(_read_job, items, context, did, workspace_id)
        return {"discovery_id": did}

    @router.get("/summary/{did}")
    def summary(did: str) -> dict[str, Any]:
        data = discoveries.get(did)
        return data["summary"] if data else {}

    @router.post("/confirm")
    def confirm(req: ConfirmRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
        data = discoveries.get(req.discovery_id)
        if not data:
            raise HTTPException(404, "unknown or expired discovery")
        job_id = uuid.uuid4().hex
        jobs = JobStore(get_settings().rdb_dsn)
        try:
            jobs.create(job_id, "documents", "confirmed entities", data.get("workspace_id", 1))
        finally:
            jobs.close()
        background_tasks.add_task(_confirm_job, req.discovery_id,
                                 req.approved_types, req.approved_files, job_id)
        return {"status": "queued", "job_id": job_id}

    return router
