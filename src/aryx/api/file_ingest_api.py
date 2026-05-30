"""File ingest API: upload JSON or CSV and run the standard pipeline.

Accepts multipart file uploads. The file is read into memory (small files for
MVP), routed to the right connector, and processed through discover → resolve
→ link → project, same as DB ingest. Job tracking is durable.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from aryx.api.admin_api import _local_broker
from aryx.config import get_settings
from aryx.connectors.base import Connector
from aryx.connectors.csv_source import CsvConnector
from aryx.connectors.json_source import JsonConnector
from aryx.pipeline.orchestrate import run_pipeline
from aryx.store.job_store import JobStore
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)

_SUPPORTED = {".json", ".csv"}


def _connector_for(data: bytes, filename: str) -> Connector:
    suffix = Path(filename).suffix.lower()
    name = Path(filename).stem
    if suffix == ".json":
        tmp = NamedTemporaryFile(suffix=".json", delete=False)
        tmp.write(data)
        tmp.close()
        return JsonConnector(Path(tmp.name), system="json")
    if suffix == ".csv":
        return CsvConnector(data, system="csv", dataset=name)
    raise ValueError(f"Unsupported file type: {suffix}")


def _run_file(data: bytes, filename: str, ontology_type: str,
              match_keys: list[str], fk_links: list[dict], job_id: str) -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    try:
        connector = _connector_for(data, filename)
        summary = run_pipeline(
            connector=connector, dsn=settings.rdb_dsn,
            system=Path(filename).suffix.lstrip("."),
            dataset=Path(filename).stem,
            ontology_type=ontology_type,
            match_keys=match_keys,
            graph_url=settings.graph_url, broker=_local_broker(),
            on_progress=lambda stage, pct, detail: jobs.update_stage(job_id, stage, pct, detail),
            fk_links=fk_links,
        )
        jobs.finish(job_id, run_id=summary.get("run_id"), status="complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("file ingest failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def file_ingest_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/ingest/file")
    async def ingest_file(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        ontology_type: str = Form(...),
        match_keys: str = Form(...),
        fk_links: str = Form("[]"),
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in _SUPPORTED:
            return {"error": f"Unsupported type {suffix}. Accepted: {_SUPPORTED}"}
        settings = get_settings()
        apply_migrations(settings.rdb_dsn)
        data = await file.read()
        job_id = uuid.uuid4().hex
        jobs = JobStore(settings.rdb_dsn)
        try:
            jobs.create(job_id, suffix.lstrip("."), Path(file.filename or "upload").stem)
        finally:
            jobs.close()
        keys = [k.strip() for k in match_keys.split(",") if k.strip()]
        links = json.loads(fk_links) if fk_links else []
        background_tasks.add_task(_run_file, data, file.filename or "upload.json",
                                  ontology_type, keys, links, job_id)
        return {"status": "queued", "job_id": job_id, "filename": file.filename}

    @router.get("/ingest/supported")
    def supported_types() -> dict[str, Any]:
        return {"file_types": sorted(_SUPPORTED),
                "note": "PDF/DOCX/PPTX available when pgvector is deployed"}

    return router
