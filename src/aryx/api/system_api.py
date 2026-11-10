"""System status API — the aryx_stat concept inside the product.

One call answers: is Postgres alive and what is PHYSICALLY stored in it,
and is the language model actually ready. The graph is read live from
Postgres, so there is no separate graph store to report on. This is the ground truth the UI shows
after (and during) every load — counts come from the stores themselves,
never from job claims.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from fastapi import APIRouter

from aryx.config import get_settings
from aryx.queries import load

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


def system_router() -> APIRouter:
    router = APIRouter(prefix="/admin")

    @router.get("/system/status")
    def system_status() -> dict[str, Any]:
        """Physical storage truth + service health, in one call."""
        pg = _pg_status()
        # LLM readiness — same probe the Brief step uses.
        from aryx.api.ask_api import _llm_probe
        llm = _llm_probe()
        return {"postgres": pg, "llm": llm}

    return router
