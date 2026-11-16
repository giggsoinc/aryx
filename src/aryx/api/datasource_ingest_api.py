"""Ingest a saved SQL datasource: POST /admin/datasources/{id}/ingest.

The request only validates (datasource exists in the caller's workspace,
connection works, requested tables exist) and queues a job; the LLM-backed
ontology mapping and the ingest itself run in the background, so a large
schema never holds the HTTP request open on the model.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.connectors.connection_errors import friendly_for_config
from aryx.connectors.schema_inspect import introspect
from aryx.job_cancel import run_cancellable
from aryx.pipeline.ingest_multi import map_and_ingest
from aryx.store.datasource_store import DatasourceStore, open_url
from aryx.store.job_store import JobStore
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)

SQL_KINDS = {"postgres", "postgresql", "mysql", "mariadb", "oracle", "sqlite"}


class DatasourceIngestRequest(BaseModel):
    """Which tables of a saved datasource to ingest (empty = all).

    ``workspace_id`` is only a guard: the job always runs in the
    datasource's own workspace, and a mismatch is treated as not found.
    """

    tables: list[str] = []
    workspace_id: int | None = None


def datasource_ingest_router() -> APIRouter:
    """Build the datasource ingest router."""
    router = APIRouter(prefix="/admin/datasources")

    @router.post("/{datasource_id}/ingest")
    def ingest_datasource(datasource_id: int, req: DatasourceIngestRequest,
                          background_tasks: BackgroundTasks) -> dict[str, Any]:
        """Queue mapping + ingest of a saved SQL datasource's tables."""
        settings = get_settings()
        store = DatasourceStore(settings.rdb_dsn)
        row = store.get(datasource_id)
        # Never cross workspaces: the stored secret belongs to the
        # datasource's workspace, so another workspace sees a 404.
        if not row or (req.workspace_id is not None
                       and req.workspace_id != row["workspace_id"]):
            raise HTTPException(404, "datasource not found")
        if row["kind"] not in SQL_KINDS:
            raise HTTPException(400, f"ingest is only supported for database "
                                     f"datasources, not '{row['kind']}'")
        workspace_id = int(row["workspace_id"])
        config = row["config"] or {}
        secret = store.secret_of(datasource_id, actor="api:ingest")
        try:
            url = open_url(row["kind"], config, secret)
            schema = introspect(url)
        except Exception as exc:
            raise HTTPException(400, friendly_for_config(exc, config, secret)) from exc
        schema = _select_tables(schema, req.tables)

        apply_migrations(settings.rdb_dsn)
        job_id = uuid.uuid4().hex
        jobs = JobStore(settings.rdb_dsn)
        try:
            jobs.create(job_id, "rdb", f"{len(schema)} table(s) from {row['name']}",
                        workspace_id)
        finally:
            jobs.close()
        background_tasks.add_task(
            run_cancellable, map_and_ingest, settings.rdb_dsn, job_id, workspace_id,
            url, schema, str(config.get("extra_context", "")), job_id, workspace_id)
        logger.info("datasource ingest queued id=%s ws=%s tables=%d job=%s",
                    datasource_id, workspace_id, len(schema), job_id)
        return {"status": "queued", "job_id": job_id,
                "tables": [t["table"] for t in schema]}

    return router


def _select_tables(schema: list[dict[str, Any]], wanted: list[str]
                   ) -> list[dict[str, Any]]:
    """Filter the introspected schema to the requested tables (empty = all)."""
    if wanted:
        unknown = set(wanted) - {t["table"] for t in schema}
        if unknown:
            raise HTTPException(400, f"unknown table(s): {', '.join(sorted(unknown))}")
        schema = [t for t in schema if t["table"] in set(wanted)]
    if not schema:
        raise HTTPException(400, "No tables found to ingest in this database.")
    return schema
