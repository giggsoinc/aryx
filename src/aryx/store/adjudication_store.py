"""Persistence for the human adjudication queue (G10).

Every queued pair — human-decided or LLM-decided — is a labeled training
example. ``merge_entities_of`` is the post-hoc union applied when a human
approves a pair after the run already materialized separate entities.

Split across three files to stay under the size cap: this module owns
construction, writes (enqueue/decide), and stats; reads (page/lookups) live
in ``adjudication_queue_reads.py`` and the merge logic in
``adjudication_merge.py`` — both mixed in below so ``AdjudicationStore``
stays the single public entry point every caller already uses.
"""
from __future__ import annotations

import os
from typing import Any

from aryx.queries import load
from aryx.store.adjudication_merge import AdjudicationMerge
from aryx.store.adjudication_queue_reads import AdjudicationQueueReads
from aryx.store.pool import get_pool


class AdjudicationStore(AdjudicationQueueReads, AdjudicationMerge):
    """Reads and writes adjudication queue rows + applies entity merges."""

    def __init__(self, dsn: str, workspace_id: int = 1) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)
        self._ws = workspace_id

    def enqueue(self, run_id: int, left_id: int, right_id: int, score: float,
                llm_verdict: float | None, llm_reason: str | None,
                status: str) -> int:
        """Insert one band pair; returns the queue row id."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_adjudication"),
                            (self._ws, run_id, left_id, right_id, score,
                             llm_verdict, llm_reason, status))
                row = cur.fetchone()
        return int(row[0]) if row else 0

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
        try:
            auto_merge = float(os.environ.get("ARYX_ER_AUTO_MERGE", 0.95))
        except ValueError:
            auto_merge = 0.95
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("adjudication_stats"), (auto_merge, self._ws))
                row = cur.fetchone()
        pending, approved, rejected, auto_llm, auto_reject, agree, overlap = row
        decided = approved + rejected
        return {
            "pending": pending, "approved": approved, "rejected": rejected,
            "auto_llm": auto_llm, "auto_reject": auto_reject,
            "approval_rate": approved / decided if decided else None,
            "human_llm_agreement": agree / overlap if overlap else None,
        }

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
