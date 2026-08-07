"""Observability API: single endpoint for the dashboard panel.

Aggregates: job pipeline health, LLM token/latency usage, graph entity/edge
counts, and model config — everything the UI needs in one call.
"""
from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter

from aryx import llm_runtime
from aryx.config import get_settings
from aryx.ports import ports
from aryx.queries import load


def _db() -> psycopg.Connection:
    return psycopg.connect(get_settings().rdb_dsn, autocommit=True)


def _job_summary(conn: psycopg.Connection, workspace_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(load("select_job_summary"), (workspace_id,))
        by_status = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute(load("select_job_total"), (workspace_id,))
        total = cur.fetchone()[0]
    return {"total": total, **by_status}


def _llm_stats(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(load("select_llm_stats"))
        row = cur.fetchone()
    stats: dict[str, Any] = {}
    if row:
        stats = {"total_calls": row[0], "total_tokens": row[1],
                "avg_latency_ms": row[2], "prompt_tokens": row[3],
                "completion_tokens": row[4]}
    stats["by_source"] = _llm_stats_by_source(conn)
    return stats


def _llm_stats_by_source(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Split ask (interactive) from pipeline (planner, ontology mapping,
    resolution, tagging — everything routed through aryx.llm.complete_json/
    complete_text) — the whole reason this table now logs pipeline calls at
    all, not just Ask's."""
    with conn.cursor() as cur:
        cur.execute(load("select_llm_stats_by_source"))
        rows = cur.fetchall()
    cols = ["source", "total_calls", "total_tokens", "avg_latency_ms",
           "prompt_tokens", "completion_tokens"]
    return [dict(zip(cols, r)) for r in rows]


def _recent_llm(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(load("select_recent_llm_calls"))
        cols = ["role", "model", "prompt_tokens", "completion_tokens",
                "latency_ms", "source", "error", "ts"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _graph_stats(workspace_id: int) -> dict[str, int]:
    try:
        reader = ports().graph_reader(workspace_id)
        return {"entities": len(reader.find_entities(limit=500)),
                "relationships": len(reader.all_relationships())}
    except Exception:
        return {"entities": 0, "relationships": 0}


def observability_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/observability")
    def observability(workspace_id: int = 1) -> dict[str, Any]:
        conn = _db()
        try:
            return {
                "jobs": _job_summary(conn, workspace_id),
                "llm": _llm_stats(conn),
                "llm_recent": _recent_llm(conn),
                "graph": _graph_stats(workspace_id),
                "model_config": llm_runtime.status(),
                "platform": ports().describe(),
            }
        finally:
            conn.close()

    return router
