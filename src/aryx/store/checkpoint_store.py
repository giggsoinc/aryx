"""Stage-level run checkpoints (G5): one durable status row per stage.

Crash semantics: a stage flips to 'running' at entry; a resumed run treats a
leftover 'running' as 'failed' (the process died mid-stage) and redoes that
stage from its own checkpoint granularity.

Per-stage idempotency: discover lands records under run_id (re-land is a new
run, so resume SKIPS done discover); resolve_keys/resolve_blocks resume via
aryx_block_done; resolve_cluster and project are wipe-rebuild idempotent;
relate and fk_link re-insert (acceptable duplication documented in G1_G5.md).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from psycopg.types.json import Json

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)

STAGES = ("discover", "resolve_keys", "resolve_blocks", "resolve_cluster",
          "relate", "fk_link", "project")


class StageTracker:
    """Reads and writes per-stage status rows for a run."""

    def __init__(self, dsn: str) -> None:
        """Acquire the shared connection pool for this DSN."""
        self._pool = get_pool(dsn)

    def _set(self, run_id: int, stage: str, status: str,
             detail: dict[str, Any] | None = None) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("upsert_run_stage"),
                            (run_id, stage, status,
                             Json(detail or {}, dumps=json.dumps)))

    def start(self, run_id: int, stage: str) -> None:
        """Mark a stage running (entry checkpoint)."""
        self._set(run_id, stage, "running")

    def finish(self, run_id: int, stage: str,
               detail: dict[str, Any] | None = None) -> None:
        """Mark a stage done with optional summary detail."""
        self._set(run_id, stage, "done", detail)

    def fail(self, run_id: int, stage: str, error: str) -> None:
        """Mark a stage failed with the error message."""
        self._set(run_id, stage, "failed", {"error": error[:500]})

    def statuses(self, run_id: int) -> dict[str, str]:
        """Stage -> status map; leftover 'running' reads as 'failed' (crash)."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_run_stages"), (run_id,))
                rows = cur.fetchall()
        return {r[0]: ("failed" if r[1] == "running" else r[1]) for r in rows}

    def rows(self, run_id: int) -> list[dict[str, Any]]:
        """Full stage rows for the resume/status API."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_run_stages"), (run_id,))
                rows = cur.fetchall()
        return [{"stage": r[0], "status": r[1], "started_at": r[2],
                 "finished_at": r[3], "detail": r[4]} for r in rows]

    def close(self) -> None:
        """No-op: connections are managed by the shared pool (G12)."""
