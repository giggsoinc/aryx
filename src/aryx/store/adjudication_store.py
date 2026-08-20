"""Persistence for the human adjudication queue (G10).

Every queued pair — human-decided or LLM-decided — is a labeled training
example. ``merge_entities_of`` is the post-hoc union applied when a human
approves a pair after the run already materialized separate entities.
"""
from __future__ import annotations

import logging
from typing import Any

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

_COLS = ("id", "run_id", "left_record_id", "right_record_id", "score",
         "llm_verdict", "llm_reason", "status", "decided_by", "decided_at",
         "created_at")


class AdjudicationStore:
    """Reads and writes adjudication queue rows + applies entity merges."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def enqueue(self, run_id: int, left_id: int, right_id: int, score: float,
                llm_verdict: bool | None, llm_reason: str | None,
                status: str) -> int:
        """Insert one band pair; returns the queue row id."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_adjudication"),
                            (self._ws, run_id, left_id, right_id, score,
                             llm_verdict, llm_reason, status))
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def page(self, status: str = "pending", limit: int = 50,
             offset: int = 0) -> list[dict[str, Any]]:
        """Return one page of queue rows with the given status."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_adjudication_page"),
                            (self._ws, status, limit, offset))
                rows = cur.fetchall()
        return [dict(zip(_COLS, r)) for r in rows]

    def decide(self, adjudication_id: int, approve: bool,
               decided_by: str) -> dict[str, Any]:
        """Flip a pending row to approved/rejected; returns the updated row.

        Raises:
            ValueError: When the row is missing or already decided.
        """
        status = "approved" if approve else "rejected"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("decide_adjudication"),
                            (status, decided_by, adjudication_id))
                row = cur.fetchone()
        if row is None:
            raise ValueError(f"adjudication {adjudication_id} not pending")
        keys = ("id", "workspace_id", "run_id", "left_record_id",
                "right_record_id", "score", "llm_verdict", "status",
                "decided_by")
        return dict(zip(keys, row))

    def stats(self) -> dict[str, Any]:
        """Queue stats incl. human/LLM agreement rate (the sales number)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("adjudication_stats"), (self._ws,))
                row = cur.fetchone()
        pending, approved, rejected, auto_llm, agree, overlap = row
        decided = approved + rejected
        return {
            "pending": pending, "approved": approved, "rejected": rejected,
            "auto_llm": auto_llm,
            "approval_rate": approved / decided if decided else None,
            "human_llm_agreement": agree / overlap if overlap else None,
        }

    def merge_entities_of(self, left_record_id: int,
                          right_record_id: int) -> bool:
        """Union the entities containing two landed records (post-hoc merge).

        The lower-id entity survives: it absorbs the other's members and the
        attribute dicts merge (survivor's values win on key collisions). The
        losing entity row is removed. Re-projection of the workspace graph is
        wipe-rebuild until G8 lands.

        Returns:
            True when a merge happened; False when already same entity or
            either record has no entity yet.
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_entity_of_record"),
                            (self._ws, left_record_id))
                left = cur.fetchone()
                cur.execute(load("select_entity_of_record"),
                            (self._ws, right_record_id))
                right = cur.fetchone()
                if not left or not right or left[0] == right[0]:
                    return False
                keep, drop = sorted((int(left[0]), int(right[0])))
                cur.execute(load("merge_entity_attributes"),
                            (keep, self._ws, drop, self._ws))
                cur.execute(load("move_entity_members"),
                            (keep, self._ws, drop))
                cur.execute(load("delete_entity_row"), (drop, self._ws))
        logger.info("entities merged keep=%s drop=%s ws=%s",
                    keep, drop, self._ws)
        return True

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
