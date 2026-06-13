"""HITL ingest questions API (Slice 3) — read pending, answer, stats.

REST shell over IngestQuestionStore. Pipeline writes; MCP/UI reads + answers.
The /enqueue endpoint exists so the pipeline (or a manual test fixture)
can push a question without a direct store import from outside.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.store.ingest_question_store import IngestQuestionStore


class EnqueueRequest(BaseModel):
    """Pipeline-side payload for raising a clarifying question."""

    workspace_id: int = 1
    job_id: str = ""
    kind: str
    prompt: str
    options: list[str] = []
    suggested: str = ""


class AnswerRequest(BaseModel):
    """Answer payload — agent or user writes back to unblock the pipeline."""

    answer: str
    answered_by: str = "agent"


def ingest_question_router() -> APIRouter:
    """Build the HITL ingest questions router."""
    router = APIRouter(prefix="/admin/ingest-questions")

    @router.get("")
    def list_questions(workspace_id: int = 1, status: str = "",
                       limit: int = 50) -> list[dict[str, Any]]:
        """List questions in a workspace; status filter ('' = all)."""
        return IngestQuestionStore(get_settings().rdb_dsn).list(
            workspace_id, status, limit)

    @router.post("")
    def enqueue_question(req: EnqueueRequest) -> dict[str, Any]:
        """Pipeline-side enqueue; returns the new question id."""
        qid = IngestQuestionStore(get_settings().rdb_dsn).enqueue(
            req.workspace_id, req.job_id, req.kind, req.prompt,
            req.options, req.suggested)
        return {"id": qid, "status": "pending"}

    @router.post("/{question_id}/answer")
    def answer_question(question_id: int,
                        req: AnswerRequest) -> dict[str, Any]:
        """Persist an answer; pipeline unblocks on its next poll."""
        try:
            return IngestQuestionStore(get_settings().rdb_dsn).answer(
                question_id, req.answer, req.answered_by)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/stats")
    def stats(workspace_id: int = 1,
              job_id: str = "") -> dict[str, int]:
        """Per-status counts for a workspace (and optional job)."""
        return IngestQuestionStore(get_settings().rdb_dsn).stats(
            workspace_id, job_id)

    return router
