"""Admin API: ingestion triggers and run status (Increment 12 UI)."""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from aryx.broker import default_broker
from aryx.config import get_settings
from aryx.connectors.postgres import PostgresConnector
from aryx.pipeline.orchestrate import run_pipeline
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)


class IngestDbRequest(BaseModel):
    table: str
    ontology_type: str
    match_keys: str
    system: str = "postgresql"
    key_column: str = "id"


def _run_db(req: IngestDbRequest) -> None:
    settings = get_settings()
    apply_migrations(settings.rdb_dsn)
    connector = PostgresConnector(
        dsn=settings.rdb_dsn, table=req.table,
        key_column=req.key_column, batch_size=settings.batch_size,
    )
    run_pipeline(
        connector=connector, dsn=settings.rdb_dsn,
        system=req.system, dataset=req.table,
        ontology_type=req.ontology_type,
        match_keys=[k.strip() for k in req.match_keys.split(",") if k.strip()],
        graph_url=settings.graph_url, broker=default_broker(),
    )
    logger.info("background ingest complete table=%s", req.table)


def admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/ingest/db")
    def ingest_db(req: IngestDbRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
        background_tasks.add_task(_run_db, req)
        return {"status": "queued", "table": req.table}

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
