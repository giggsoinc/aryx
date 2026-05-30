"""Ask API — natural-language questions answered over the knowledge graph.

Built on the existing Broker (provider routing + tiers + token charge-back).
Flow: menial tier extracts search terms (thinking off) -> deterministic graph
retrieval -> reason tier synthesises the answer. Returns the answer, the graph
calls made, and token/latency usage for observability.
"""
from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from aryx.broker import Broker, ModelSpec, Registry, TokenGovernor
from aryx.config import get_settings
from aryx.graph import GraphReader
from aryx.graph.retrieve import all_types, retrieve
from aryx.llm import complete_text

logger = logging.getLogger(__name__)

_OLLAMA = os.environ.get("ARYX_LLM_BASE_URL", "http://localhost:11434")
_MENIAL = os.environ.get("ARYX_LLM_MENIAL_MODEL", "qwen3.5:0.8b")
_REASON = os.environ.get("ARYX_LLM_REASON_MODEL", "lfm2.5-thinking")


@lru_cache(maxsize=1)
def _reader() -> GraphReader:
    return GraphReader(get_settings().graph_url)


@lru_cache(maxsize=1)
def _broker() -> Broker:
    """Local-only broker: menial=cheap (qwen), reason=frontier (lfm). Cloud
    providers are opt-in via the Settings panel, not bundled here by default."""
    registry = Registry()
    registry.add(ModelSpec(name=_MENIAL, provider="ollama", tier="cheap",
                           local=True, endpoint=_OLLAMA))
    registry.add(ModelSpec(name=_REASON, provider="ollama", tier="frontier",
                           local=True, endpoint=_OLLAMA))
    return Broker(registry, TokenGovernor({}))


class AskRequest(BaseModel):
    question: str


def _extract_terms(question: str, types: list[str]) -> tuple[list[str], int, int, int]:
    sys = "Extract the specific search terms a graph lookup needs."
    user = (
        "From the question, pull 1-3 specific names, ticket refs, or keywords to "
        "search for. Do NOT include generic category words like "
        f"{', '.join(types)}. Reply ONLY as JSON {{\"terms\": [\"...\"]}}.\n"
        f"Question: {question}"
    )
    start = time.monotonic()
    text, it, ot = complete_text(_broker(), "cheap", sys, user, think=False)
    ms = int((time.monotonic() - start) * 1000)
    try:
        s, e = text.find("{"), text.rfind("}")
        terms = json.loads(text[s:e + 1]).get("terms", [])
    except (ValueError, json.JSONDecodeError):
        terms = []
    return ([t for t in terms if t] or [question.strip()]), it, ot, ms


def _synthesise(question: str, context: str) -> tuple[str, int, int, int]:
    sys = "You are Aryx, a knowledge-graph assistant."
    user = (
        "Answer using ONLY the graph facts below. Be concise; cite entities by "
        "name; if the facts don't cover it, say so.\n\n"
        f"GRAPH FACTS:\n{context}\n\nQUESTION: {question}"
    )
    start = time.monotonic()
    text, it, ot = complete_text(_broker(), "frontier", sys, user, think=False)
    ms = int((time.monotonic() - start) * 1000)
    return text, it, ot, ms


def ask_router() -> APIRouter:
    router = APIRouter()

    @router.post("/ask")
    def ask(req: AskRequest) -> dict:
        reader = _reader()
        types = all_types(reader)
        try:
            terms, p_in, p_out, p_ms = _extract_terms(req.question, types)
            context, calls = retrieve(reader, terms)
            answer, s_in, s_out, s_ms = _synthesise(req.question, context)
        except Exception as exc:  # noqa: BLE001 — surface model/runtime errors to UI
            logger.warning("ask failed: %s", exc)
            return {"answer": f"LLM unavailable (models may still be loading): {exc}",
                    "terms": [], "tools_called": [], "usage": {}}
        return {
            "answer": answer or "No answer produced.",
            "terms": terms,
            "tools_called": calls,
            "usage": {
                "prompt_tokens": p_in + s_in,
                "completion_tokens": p_out + s_out,
                "latency_ms": p_ms + s_ms,
                "menial_model": _MENIAL,
                "reason_model": _REASON,
            },
        }

    return router
