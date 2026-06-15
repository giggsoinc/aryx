"""Accuracy Lab API (v2 Phase 1) — ontology on/off A/B over the graph.

Runs the SAME model on the SAME question twice: ON answers grounded in the
resolved knowledge graph (identical to the real Ask path), OFF answers with no
workspace grounding. The scorecard contrasts grounded-with-citations vs
asserted — the proof an enterprise skeptic asks for.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from aryx import llm_runtime
from aryx.api.ask_api import _extract_terms, _reader, _strip_think, _synthesise
from aryx.api.ask_overview import build as build_overview
from aryx.ask import run_ab
from aryx.graph.retrieve import all_types, gather, render_context

logger = logging.getLogger(__name__)

_OFF_SYS = "You are a general assistant answering from your own knowledge."
_OFF_USER = (
    "Answer the question. You have NO access to the user's data, database, or "
    "knowledge graph — answer only from general knowledge. QUESTION: {q}"
)


def _answer_off(question: str) -> str:
    """The baseline: same model, no workspace grounding at all."""
    text, _, _ = llm_runtime.chat("answer", _OFF_SYS, _OFF_USER.format(q=question))
    return _strip_think(text)


class AbRequest(BaseModel):
    question: str
    workspace_id: int = 1


def lab_router() -> APIRouter:
    router = APIRouter(prefix="/lab")

    @router.post("/ab")
    def ab(req: AbRequest) -> dict:
        """Ontology on/off comparison for one question."""
        reader = _reader(req.workspace_id)
        try:
            types = all_types(reader)
            overview = build_overview(reader, req.workspace_id)
            terms, *_ = _extract_terms(req.question, types, [])
            entities, _calls = gather(reader, terms)
            context = render_context(entities)
            answer_on, *_ = _synthesise(req.question, context, overview)
            answer_off = _answer_off(req.question)
        except Exception as exc:  # noqa: BLE001 — surface to the Lab UI
            logger.warning("lab ab failed: %s", exc)
            return {"error": f"LLM unavailable: {exc}"}
        model = llm_runtime.status().get("answer_model", "")
        return run_ab(req.question, entities, answer_on, answer_off, model).to_dict()

    @router.get("/reasoner")
    def reasoner(workspace_id: int = 1) -> dict:
        """Read-only: how many contradictions the axioms would block right now."""
        from aryx.config import get_settings
        from aryx.reasoning.axiom_validator import validate_workspace
        try:
            summary = validate_workspace(workspace_id, get_settings().rdb_dsn,
                                         record=False)
        except Exception as exc:  # noqa: BLE001 — surface to the Lab UI
            logger.warning("lab reasoner failed: %s", exc)
            return {"error": f"reasoner unavailable: {exc}"}
        return {**summary, "blocked": summary.get("violations", 0)}

    return router
