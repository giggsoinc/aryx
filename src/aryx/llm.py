"""Unified model completion: route a tiered request to the chosen provider.

The Broker decides which model serves a tier; this calls it. Three wire paths:
- 'anthropic'  -> Claude SDK (structured outputs)
- 'ollama'     -> native Ollama JSON mode
- anything else-> OpenAI-compatible /chat/completions (Grok, Gemini, vLLM, ...)

Token usage is charged back to the governor so budgets actually bite.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from typing import Any

import psycopg

from aryx.broker import Broker
from aryx.broker.specs import Tier
from aryx.config import get_settings
from aryx.llm_normalize import normalize as _normalize_json
from aryx.llm_providers import (
    anthropic_json, ollama_json, openai_json, post_json,
)
from aryx.queries import load

logger = logging.getLogger(__name__)

# Re-export so legacy callers keep working.
_post_json = post_json
_anthropic_json = anthropic_json
_ollama_json = ollama_json
_openai_json = openai_json


def _log_call(role: str, model: str, provider: str, pt: int, ct: int,
              ms: int, source: str) -> None:
    """Best-effort persist to aryx_llm_call (no-op if DB unavailable) — same
    table/shape `llm_runtime.chat` (the Ask tab) already writes to, tagged
    `source` so the observability panel can split interactive Ask usage from
    this shared production dispatcher's usage (planner, ontology mapping,
    resolution, tagging, and everything else routed through complete_json/
    complete_text). Only successful calls are logged, matching the Ask
    path's own existing convention."""
    try:
        dsn = get_settings().rdb_dsn
    except Exception:  # noqa: BLE001 — logging must never break a real call
        return
    if not dsn:
        return
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_llm_call"),
                           (role, model, provider, pt, ct, ms, source, None))
    except Exception:  # noqa: BLE001
        logger.debug("llm call log write failed", exc_info=True)


def _fallback_spec(spec: Any, exc: Exception) -> Any:
    """Local-Ollama fallback spec for QUOTA/TRANSIENT failures — or None.

    Auth failures (401/403 — bad or blocked key) return None on purpose:
    silently masking a broken key with a weaker local model produces
    mystery-quality output. Quota (429), 5xx, and connection errors fall
    back so an exhausted free tier never kills an ingest.
    """
    import os

    from aryx.broker import ModelSpec
    if getattr(spec, "provider", "") == "ollama":
        return None
    msg = str(exc)
    transient = ("429" in msg or "RESOURCE_EXHAUSTED" in msg
                 or "quota" in msg.lower() or " 50" in msg[:80]
                 or "Connection" in msg or "timed out" in msg.lower())
    if not transient:
        return None
    endpoint = os.environ.get("ARYX_LLM_BASE_URL", "http://ollama:11434")
    model = os.environ.get("ARYX_LLM_REASON_MODEL", "lfm2.5-thinking:latest")
    return ModelSpec(name=model, provider="ollama", tier="cheap",
                     local=True, endpoint=endpoint, api_key_ref=None)


def complete_text(
    broker: Broker, tier: Tier, system: str, user: str,
    think: bool | None = None,
) -> tuple[str, int, int]:
    """Plain-text completion at the given tier; returns (text, in_tok, out_tok).

    `think` toggles hybrid-model reasoning on the Ollama path (False keeps fast
    models off thinking for menial work). Token counts let callers meter usage.
    """
    import json
    spec = broker.choose(tier)
    key = broker.secrets.get(spec.api_key_ref) if spec.api_key_ref else None
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    start = time.monotonic()
    if spec.provider == "anthropic":
        import anthropic  # lazy: only on the Anthropic path
        client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        resp = client.messages.create(model=spec.name, max_tokens=1024,
                                       system=system,
                                       messages=[{"role": "user", "content": user}])
        text = next(b.text for b in resp.content if b.type == "text")
        in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    elif spec.provider == "ollama":
        body: dict[str, Any] = {"model": spec.name, "stream": False,
                                "messages": msgs,
                                "options": {"temperature": 0.2,
                                            "num_predict": 512}}
        if think is not None:
            body["think"] = think
        out = post_json((spec.endpoint or "").rstrip("/") + "/api/chat",
                        body, {})
        text = out["message"]["content"]
        in_tok = int(out.get("prompt_eval_count", 0))
        out_tok = int(out.get("eval_count", 0))
    else:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            out = post_json((spec.endpoint or "").rstrip("/") + "/chat/completions",
                            {"model": spec.name, "messages": msgs}, headers)
        except Exception as exc:  # noqa: BLE001 — try local fallback
            fb = _fallback_spec(spec, exc)
            if fb is None:
                raise
            logger.warning("llm fallback → ollama/%s (provider %s failed: %.120s)",
                           fb.name, spec.provider, str(exc))
            out = post_json((fb.endpoint or "").rstrip("/") + "/api/chat",
                            {"model": fb.name, "stream": False,
                             "messages": msgs, "think": False}, {})
            text = out["message"]["content"]
            in_tok = int(out.get("prompt_eval_count", 0))
            out_tok = int(out.get("eval_count", 0))
            broker.charge(tier, in_tok + out_tok)
            _ = json
            return text.strip(), in_tok, out_tok
        text = out["choices"][0]["message"]["content"]
        u = out.get("usage", {})
        in_tok = int(u.get("prompt_tokens", 0))
        out_tok = int(u.get("completion_tokens", 0))
    broker.charge(tier, in_tok + out_tok)
    _log_call(str(tier), spec.name, spec.provider, in_tok, out_tok,
             int((time.monotonic() - start) * 1000), "pipeline")
    _ = json  # quiet linter — used transitively
    return text.strip(), in_tok, out_tok


def complete_json(
    broker: Broker, tier: Tier, system: str, user: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Run a structured-JSON completion at the given tier via the Broker.

    Returns the parsed JSON object the model produced, normalized to the
    schema shape (envelope coercion + synonym renaming via llm_normalize).
    """
    spec = broker.choose(tier)
    key = broker.secrets.get(spec.api_key_ref) if spec.api_key_ref else None
    start = time.monotonic()
    try:
        if spec.provider == "anthropic":
            data, in_tok, out_tok = anthropic_json(spec, system, user, schema, key)
        elif spec.provider == "ollama":
            data, in_tok, out_tok = ollama_json(spec, system, user)
        else:
            data, in_tok, out_tok = openai_json(spec, system, user, key)
    except Exception as exc:  # noqa: BLE001 — try the local fallback path
        fb = _fallback_spec(spec, exc)
        if fb is None:
            raise
        logger.warning("llm fallback → ollama/%s (provider %s failed: %.120s)",
                       fb.name, spec.provider, str(exc))
        data, in_tok, out_tok = ollama_json(fb, system, user)
    broker.charge(tier, in_tok + out_tok)
    logger.info("complete tier=%s provider=%s model=%s tokens=%d", tier,
                spec.provider, spec.name, in_tok + out_tok)
    _log_call(str(tier), spec.name, spec.provider, in_tok, out_tok,
             int((time.monotonic() - start) * 1000), "pipeline")
    # Provider-quirk normalization: list-vs-dict envelope + synonym rename.
    return _normalize_json(data, schema)
