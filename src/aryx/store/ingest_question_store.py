"""CRUD over aryx_ingest_question — the HITL questions queue (Slice 3).

The pipeline pushes clarifying questions (entity collapse candidates,
ambiguous type mappings, FK match disambiguation). External agents read
pending rows via MCP, route them to the user, write answers back. The
pipeline polls answered rows on its next stage iteration.
"""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class IngestQuestionStore:
    """Pending-or-answered questions raised during an ingest job."""

    def __init__(self, dsn: str) -> None:
        self._pool = get_pool(dsn)

    def enqueue(self, workspace_id: int, job_id: str, kind: str,
                prompt: str, options: list[str] | None = None,
                suggested: str = "") -> int:
        """Insert one question; returns its id."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("insert_ingest_question"), {
                "workspace_id": int(workspace_id),
                "job_id": job_id or "", "kind": kind, "prompt": prompt,
                "options_json": Json(options or []),
                "suggested": suggested})
            row = cur.fetchone()
        logger.info("ingest question enqueued id=%s ws=%s kind=%s",
                    row[0], workspace_id, kind)
        return int(row[0])

    def list(self, workspace_id: int, status: str = "",
             limit: int = 50) -> list[dict[str, Any]]:
        """List questions for a workspace; status='' returns all statuses."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("select_ingest_questions"), {
                "workspace_id": int(workspace_id),
                "status": status or "", "limit": int(limit)})
            return [self._row(r) for r in cur.fetchall()]

    def answer(self, question_id: int, answer: str,
               actor: str = "agent") -> dict[str, Any]:
        """Persist an answer + unblock the pipeline on next poll."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("answer_ingest_question"), {
                "id": int(question_id), "answer": answer,
                "answered_by": actor})
            row = cur.fetchone()
        if not row:
            raise ValueError(f"ingest question {question_id} not found")
        logger.info("ingest question answered id=%s actor=%s",
                    question_id, actor)
        return {"id": int(row[0]), "status": row[1], "answer": row[2]}

    def stats(self, workspace_id: int,
              job_id: str = "") -> dict[str, int]:
        """Return per-status counts for a workspace (and optional job)."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("count_ingest_questions"), {
                "workspace_id": int(workspace_id),
                "job_id": job_id or ""})
            return {str(r[0]): int(r[1]) for r in cur.fetchall()}

    @staticmethod
    def _row(r: tuple) -> dict[str, Any]:
        """Project a row tuple into the JSON-friendly question dict."""
        return {"id": r[0], "workspace_id": r[1], "job_id": r[2],
                "kind": r[3], "prompt": r[4], "options": r[5] or [],
                "suggested": r[6], "status": r[7], "answer": r[8],
                "answered_by": r[9], "created_at": r[10],
                "answered_at": r[11]}
