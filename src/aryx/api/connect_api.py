"""Connection + auto-discovery + multi-table ingest API.

Flow: POST /admin/connect (test + introspect) → POST /admin/discover (agent
proposes ontology mapping) → POST /admin/ingest/multi (ingest confirmed tables
and create the relationship edges). Works for any SQLAlchemy-reachable RDBMS.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from aryx import connections
from aryx.config import get_settings
from aryx.connectors.connection_errors import friendly_db_error
from aryx.connectors.schema_inspect import introspect, test_connection
from aryx.pipeline.ingest_multi import run_multi
from aryx.pipeline.schema_agent import discover_mappings
from aryx.store.datasource_store import build_url
from aryx.store.job_store import JobStore
from aryx.job_cancel import run_cancellable
from aryx.store.migrate import apply_migrations

logger = logging.getLogger(__name__)

_DRIVERS = {
    "postgresql": "postgresql+psycopg", "mysql": "mysql+pymysql",
    "mariadb": "mysql+pymysql", "oracle": "oracle+oracledb", "sqlite": "sqlite",
}


class ConnectRequest(BaseModel):
    dialect: str = "postgresql"
    host: str = ""
    port: str = ""
    database: str = ""
    user: str = ""
    password: str = ""
    url: str = ""


class DiscoverRequest(BaseModel):
    connection_id: str
    context: str


class IngestMultiRequest(BaseModel):
    connection_id: str
    tables: list[dict]
    edges: list[dict] = []
    workspace_id: int = 1


def _build_url(req: ConnectRequest) -> str:
    if req.url:
        return req.url
    if req.dialect not in _DRIVERS:
        raise HTTPException(400, f"unsupported dialect: {req.dialect}")
    try:
        return build_url(req.dialect, host=req.host, port=req.port,
                         database=req.database, user=req.user,
                         password=req.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def connect_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/connect")
    def connect(req: ConnectRequest) -> dict[str, Any]:
        url = _build_url(req)
        try:
            test_connection(url)
            schema = introspect(url)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                400, friendly_db_error(exc, host=req.host, port=req.port,
                                       database=req.database,
                                       secret=req.password)) from exc
        return {"connection_id": connections.put(url),
                "tables": [t["table"] for t in schema], "schema": schema}

    @router.post("/discover")
    def discover(req: DiscoverRequest) -> dict[str, Any]:
        url = connections.get(req.connection_id)
        if not url:
            raise HTTPException(404, "unknown connection")
        return discover_mappings(introspect(url), req.context)

    @router.post("/ingest/multi")
    def ingest_multi(req: IngestMultiRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
        url = connections.get(req.connection_id)
        if not url:
            raise HTTPException(404, "unknown connection")
        settings = get_settings()
        apply_migrations(settings.rdb_dsn)
        job_id = uuid.uuid4().hex
        jobs = JobStore(settings.rdb_dsn)
        try:
            jobs.create(job_id, "rdb", f"{len(req.tables)} table(s)", req.workspace_id)
        finally:
            jobs.close()
        background_tasks.add_task(run_cancellable, run_multi, settings.rdb_dsn, job_id,
                                  req.workspace_id, url, req.tables, req.edges, job_id,
                                  req.workspace_id)
        return {"status": "queued", "job_id": job_id,
                "tables": [t["table"] for t in req.tables]}

    return router
