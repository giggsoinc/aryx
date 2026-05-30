"""Admin API: ingestion triggers with durable per-stage job progress."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import psycopg
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from aryx.broker import default_broker
from aryx.config import get_settings
from aryx.connectors.postgres import PostgresConnector
from aryx.pipeline.orchestrate import run_pipeline
from aryx.store.job_store import JobStore
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)


class FkLink(BaseModel):
    source_type: str
    source_attr: str
    target_type: str
    target_attr: str
    name: str


class IngestDbRequest(BaseModel):
    table: str
    ontology_type: str
    match_keys: str
    system: str = "postgresql"
    key_column: str = "id"
    fk_links: list[FkLink] = []


def _run_db(req: IngestDbRequest, job_id: str) -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    try:
        connector = PostgresConnector(
            dsn=settings.rdb_dsn, table=req.table,
            key_column=req.key_column, batch_size=settings.batch_size,
        )
        summary = run_pipeline(
            connector=connector, dsn=settings.rdb_dsn,
            system=req.system, dataset=req.table,
            ontology_type=req.ontology_type,
            match_keys=[k.strip() for k in req.match_keys.split(",") if k.strip()],
            graph_url=settings.graph_url, broker=default_broker(),
            on_progress=lambda stage, pct, detail: jobs.update_stage(job_id, stage, pct, detail),
            fk_links=[link.model_dump() for link in req.fk_links],
        )
        jobs.finish(job_id, run_id=summary.get("run_id"), status="complete")
    except Exception as exc:  # noqa: BLE001 — record failure for the dashboard
        logger.warning("ingest failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/ingest/db")
    def ingest_db(req: IngestDbRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
        settings = get_settings()
        apply_migrations(settings.rdb_dsn)
        jobs = JobStore(settings.rdb_dsn)
        job_id = uuid.uuid4().hex
        try:
            jobs.archive_old(30)
            jobs.create(job_id, req.system, req.table)
        finally:
            jobs.close()
        background_tasks.add_task(_run_db, req, job_id)
        return {"status": "queued", "job_id": job_id, "table": req.table}

    @router.get("/runs")
    def list_runs() -> list[dict[str, Any]]:
        settings = get_settings()
        with psycopg.connect(settings.rdb_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT run_id, source_system, source_dataset, status, "
                    "record_count, started_at, finished_at "
                    "FROM aryx_run ORDER BY run_id DESC LIMIT 50"
                )
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]

    return router
