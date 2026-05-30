"""Ask API — natural-language questions answered over the knowledge graph.

Flow: menial model extracts search terms -> deterministic graph retrieval ->
reason model synthesises the answer. Returns the answer, the graph calls made,
and token/latency usage for observability.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from aryx.config import get_settings
from aryx.graph import GraphReader
from aryx.llm import client, config, router, tools

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _reader() -> GraphReader:
    return GraphReader(get_settings().graph_url)


class AskRequest(BaseModel):
    question: str


def _extract_terms(question: str, types: list[str], cfg: config.LlmConfig) -> tuple[list[str], client.ChatResult]:
    model, think = router.pick("menial", cfg)
    prompt = (
        "Extract 1-3 short search terms (company names, ticket refs, keywords) "
        f"from this question. Known entity types: {', '.join(types)}. "
        'Reply ONLY as JSON: {"terms": ["..."]}. Question: ' + question
    )
    res = client.chat([{"role": "user", "content": prompt}], model, cfg, think)
    terms: list[str] = []
    try:
        start, end = res.content.find("{"), res.content.rfind("}")
        terms = json.loads(res.content[start:end + 1]).get("terms", [])
    except (ValueError, json.JSONDecodeError):
        terms = []
    return ([t for t in terms if t] or [question.strip()]), res


def _synthesise(question: str, context: str, cfg: config.LlmConfig) -> client.ChatResult:
    model, think = router.pick("reason", cfg)
    prompt = (
        "You are Aryx, a knowledge-graph assistant. Answer the question using ONLY "
        "the graph facts below. Be concise; cite entities by name; if the facts do "
        f"not cover it, say so.\n\nGRAPH FACTS:\n{context}\n\nQUESTION: {question}"
    )
    return client.chat([{"role": "user", "content": prompt}], model, cfg, think)


def ask_router() -> APIRouter:
    router_ = APIRouter()

    @router_.post("/ask")
    def ask(req: AskRequest) -> dict:
        cfg = config.effective()
        reader = _reader()
        types = tools.all_types(reader)

        terms, parse = _extract_terms(req.question, types, cfg)
        context, calls = tools.retrieve(reader, terms)
        synth = _synthesise(req.question, context, cfg)

        err = parse.error or synth.error
        answer = synth.content or (f"LLM unavailable: {err}" if err else "No answer produced.")
        return {
            "answer": answer,
            "terms": terms,
            "tools_called": calls,
            "usage": {
                "prompt_tokens": parse.prompt_tokens + synth.prompt_tokens,
                "completion_tokens": parse.completion_tokens + synth.completion_tokens,
                "latency_ms": parse.latency_ms + synth.latency_ms,
                "menial_model": parse.model,
                "reason_model": synth.model,
            },
            "error": err,
        }

    @router_.get("/llm/config")
    def llm_config() -> dict:
        return config.status()

    return router_
