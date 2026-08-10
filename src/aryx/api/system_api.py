"""System status API — the aryx_stat concept inside the product.

One call answers: is Postgres alive and what is PHYSICALLY stored in it,
is FalkorDB alive and what is projected into each workspace graph, and is
the language model actually ready. This is the ground truth the UI shows
after (and during) every load — counts come from the stores themselves,
never from job claims.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import APIRouter

from aryx.config import get_settings
from aryx.graph.falkor_store import FalkorStore
from aryx.queries import load
from aryx.workspaces import ws_graph

logger = logging.getLogger(__name__)


def _pg_status() -> dict[str, Any]:
    settings = get_settings()
    try:
        with psycopg.connect(settings.rdb_dsn, autocommit=True,
                             connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_db_size"))
                size = cur.fetchone()[0]
                cur.execute(load("select_workspaces"))
                workspaces = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
                rows = []
                for ws in workspaces:
                    wid = ws["id"]
                    counts = {}
                    for key, q in (("landed_records", "count_landed"),
                                   ("entities", "count_entities"),
                                   ("relationships", "count_relationships")):
                        cur.execute(load(q), (wid,))
                        counts[key] = int(cur.fetchone()[0])
                    rows.append({**ws, **counts})
                # Document chunks are global (keyed by doc, not workspace).
                cur.execute(load("count_chunks"))
                chunks = int(cur.fetchone()[0])
                cur.execute(load("count_chunk_embeddings"))
                embeddings = int(cur.fetchone()[0])
        return {"ok": True, "db_size": size, "workspaces": rows,
                "doc_chunks": chunks, "chunk_embeddings": embeddings}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "workspaces": []}


def _graph_status(workspace_ids: list[int]) -> dict[str, Any]:
    settings = get_settings()
    graphs = []
    try:
        for wid in workspace_ids:
            try:
                store = FalkorStore(settings.graph_url, ws_graph(wid))
                graphs.append({"workspace_id": wid, **store.counts()})
            except Exception:  # noqa: BLE001 — graph may not exist yet
                graphs.append({"workspace_id": wid, "nodes": 0, "edges": 0})
        return {"ok": True, "graphs": graphs}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "graphs": graphs}


def system_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/system/status")
    def system_status() -> dict[str, Any]:
        """Physical storage truth + service health, in one call."""
        pg = _pg_status()
        wids = [w["id"] for w in pg.get("workspaces", [])]
        graph = _graph_status(wids)
        # LLM readiness — same probe the Brief step uses.
        from aryx.api.ask_api import _llm_probe
        llm = _llm_probe()
        return {"postgres": pg, "falkordb": graph, "llm": llm}

    return router
