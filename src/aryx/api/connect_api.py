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
from aryx.api.admin_api import _local_broker
from aryx.config import get_settings
from aryx.connectors.schema_inspect import introspect, test_connection
from aryx.connectors.sql_source import SqlConnector
from aryx.pipeline.orchestrate import run_pipeline
from aryx.pipeline.schema_agent import discover_mappings
from aryx.store.job_store import JobStore
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
    driver = _DRIVERS.get(req.dialect)
    if not driver:
        raise HTTPException(400, f"unsupported dialect: {req.dialect}")
    if req.dialect == "sqlite":
        return f"sqlite:///{req.database}"
    auth = f"{req.user}:{req.password}@" if req.user else ""
    port = f":{req.port}" if req.port else ""
    return f"{driver}://{auth}{req.host}{port}/{req.database}"


def _run_multi(url: str, tables: list[dict], edges: list[dict], job_id: str,
               workspace_id: int = 1) -> None:
    settings = get_settings()
    jobs = JobStore(settings.rdb_dsn)
    broker = _local_broker()
    try:
        total = len(tables)
        for i, t in enumerate(tables):
            pct = int(10 + i * 80 / max(total, 1))
            jobs.update_stage(job_id, f"Table {i + 1}/{total}", pct, f"Ingesting {t['table']}")
            keys = t.get("match_keys") or ["id"]
            run_pipeline(
                connector=SqlConnector(url, t["table"], keys[0], system="rdb"),
                dsn=settings.rdb_dsn, system="rdb", dataset=t["table"],
                ontology_type=t["ontology_type"], match_keys=keys,
                graph_url=settings.graph_url, broker=broker,
                workspace_id=workspace_id,
                fk_links=edges if i == total - 1 else [],
            )
        jobs.finish(job_id, run_id=None, status="complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("multi ingest failed job=%s: %s", job_id, exc)
        jobs.finish(job_id, run_id=None, status="failed", error=str(exc))
    finally:
        jobs.close()


def connect_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.post("/connect")
    def connect(req: ConnectRequest) -> dict[str, Any]:
        url = _build_url(req)
        try:
            test_connection(url)
            schema = introspect(url)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"connection failed: {exc}") from exc
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
        background_tasks.add_task(_run_multi, url, req.tables, req.edges, job_id, req.workspace_id)
        return {"status": "queued", "job_id": job_id,
                "tables": [t["table"] for t in req.tables]}

    return router
