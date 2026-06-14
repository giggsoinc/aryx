"""Ask API — natural-language questions answered over the knowledge graph.

Flow: extract terms -> deterministic graph retrieval -> synthesise -> verify
grounding. Returns the answer, graph calls, usage, and the grounding record.
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel

from aryx import llm_runtime
from aryx.api.ask_overview import build as build_overview
from aryx.ask import build_grounding
from aryx.config import get_settings
from aryx.graph.retrieve import all_types, gather, render_context
from aryx.ports import GraphReaderPort, ports
from aryx.store.ask_history_store import AskHistoryStore

logger = logging.getLogger(__name__)


def _reader(workspace_id: int = 1) -> GraphReaderPort:
    return ports().graph_reader(workspace_id)


class Turn(BaseModel):
    role: str
    text: str


class AskRequest(BaseModel):
    question: str
    history: list[Turn] = []
    workspace_id: int = 1


def _strip_think(text: str) -> str:
    """Drop any <think> chain-of-thought a model inlines into its answer."""
    text = text.rsplit("</think>", 1)[-1] if "</think>" in text else text
    return text.replace("<think>", "").strip()


def _recent(history: list[Turn], limit: int = 4) -> str:
    if not history:
        return ""
    turns = history[-limit:]
    return "\n".join(f"{t.role}: {t.text}" for t in turns)


def _extract_terms(question: str, types: list[str], history: list[Turn]) -> tuple[list[str], int, int, int]:
    context = _recent(history)
    sys = "Extract the specific search terms a graph lookup needs."
    user = (
        "Using the recent conversation to resolve pronouns (it, they, this), pull "
        "1-3 specific names, ticket refs, or keywords from the CURRENT question. "
        f"Do NOT include generic category words like {', '.join(types)}. "
        'Reply ONLY as JSON {"terms": ["..."]}.\n'
        f"{('Recent conversation:' + chr(10) + context + chr(10)) if context else ''}"
        f"CURRENT question: {question}"
    )
    start = time.monotonic()
    text, it, ot = llm_runtime.chat("menial", sys, user)
    ms = int((time.monotonic() - start) * 1000)
    try:
        s, e = text.find("{"), text.rfind("}")
        terms = json.loads(text[s:e + 1]).get("terms", [])
    except (ValueError, json.JSONDecodeError):
        terms = []
    return ([t for t in terms if t] or [question.strip()]), it, ot, ms


def _synthesise(question: str, context: str, overview: str = "") -> tuple[str, int, int, int]:
    sys = "You are Aryx, a knowledge-graph assistant."
    has_context = bool(context.strip())
    facts = context if has_context else "(none — no specific entity matched)"
    user = (
        "Answer the question grounded in the workspace below. If GRAPH FACTS "
        "contains a specific entity, ground the answer there. If GRAPH FACTS "
        "is empty, use the OVERVIEW to describe what's in the workspace — "
        "DO NOT say 'no matching entities' or 'not stored'; instead, tell "
        "the user what is tracked and suggest the next concrete question.\n\n"
        f"{overview}\n\nGRAPH FACTS:\n{facts}\n\nQUESTION: {question}"
    )
    start = time.monotonic()
    text, it, ot = llm_runtime.chat("answer", sys, user)
    ms = int((time.monotonic() - start) * 1000)
    return _strip_think(text), it, ot, ms


class LlmConfigRequest(BaseModel):
    provider: str = ""
    menial_model: str = ""
    answer_model: str = ""
    endpoint: str = ""
    api_key: str = ""


def ask_router() -> APIRouter:
    router = APIRouter()

    @router.post("/ask")
    def ask(req: AskRequest) -> dict:
        reader = _reader(req.workspace_id)
        types = all_types(reader)
        overview = build_overview(reader, req.workspace_id)
        try:
            terms, p_in, p_out, p_ms = _extract_terms(req.question, types, req.history)
            entities, calls = gather(reader, terms)
            context = render_context(entities)
            answer, s_in, s_out, s_ms = _synthesise(req.question, context, overview)
            grounding = build_grounding(answer or "", entities)
        except Exception as exc:  # noqa: BLE001 — surface model/runtime errors to UI
            logger.warning("ask failed: %s", exc)
            return {"answer": f"LLM unavailable: {exc}", "terms": [],
                    "tools_called": [], "usage": {}, "grounding": None}
        cfg = llm_runtime.status()
        usage = {
            "prompt_tokens": p_in + s_in,
            "completion_tokens": p_out + s_out,
            "latency_ms": p_ms + s_ms,
            "menial_model": cfg["menial_model"],
            "answer_model": cfg["answer_model"],
        }
        try:
            hstore = AskHistoryStore(get_settings().rdb_dsn)
            try:
                hstore.append(req.workspace_id, req.question,
                              answer or "", calls, [], usage)
            finally:
                hstore.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ask history persist failed: %s", exc)
        return {"answer": answer or "No answer produced.", "terms": terms,
                "tools_called": calls, "usage": usage,
                "grounding": grounding.to_dict()}

    @router.get("/llm/config")
    def get_llm_config() -> dict:
        return llm_runtime.status()

    @router.post("/admin/llm/config")
    def set_llm_config(req: LlmConfigRequest) -> dict:
        llm_runtime.set_config(**req.model_dump())
        return llm_runtime.status()

    return router
