"""Ask history store — persist every Q/A turn for cross-session recall + audit."""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class AskHistoryStore:
    """CRUD over aryx_ask_history scoped by workspace."""

    def __init__(self, dsn: str) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)

    def append(self, workspace_id: int, question: str, answer: str,
               tools_called: list, entity_ids: list[int],
               usage: dict[str, Any]) -> dict[str, Any]:
        """Insert one Q/A turn; return id + timestamp."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_ask_history"), (
                    int(workspace_id), question, answer,
                    Json(tools_called or []),
                    [int(x) for x in (entity_ids or [])],
                    int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)),
                    int(usage.get("latency_ms", 0)),
                    str(usage.get("answer_model", "")),
                ))
                row = cur.fetchone()
        return {"id": row[0], "asked_at": row[1]}

    def recent(self, workspace_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent N rows for a workspace, newest first."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_ask_history"),
                            (int(workspace_id), int(limit)))
                rows = cur.fetchall()
        return [{
            "id": r[0], "workspace_id": r[1], "asked_at": r[2],
            "question": r[3], "answer": r[4], "tools_called": r[5],
            "entity_ids": list(r[6] or []),
            "prompt_tokens": r[7], "completion_tokens": r[8],
            "latency_ms": r[9], "answer_model": r[10],
        } for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
