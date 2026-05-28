"""Unified model completion: route a tiered request to the chosen provider.

The Broker decides which model serves a tier; this calls it. Three wire paths:
- 'anthropic'  -> Claude SDK (structured outputs)
- 'ollama'     -> native Ollama JSON mode
- anything else-> OpenAI-compatible /chat/completions (Grok, Gemini, vLLM, ...)

Token usage is charged back to the governor so budgets actually bite.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from aryx.broker import Broker
from aryx.broker.specs import ModelSpec, Tier

logger = logging.getLogger(__name__)


def _anthropic_json(
    spec: ModelSpec, system: str, user: str, schema: dict[str, Any], key: str | None
) -> tuple[dict[str, Any], int, int]:
    """Call a Claude model with structured JSON output."""
    import anthropic  # lazy: only on the Anthropic path

    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    resp = client.messages.create(
        model=spec.name,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), resp.usage.input_tokens, resp.usage.output_tokens


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str],
               timeout: float = 120.0) -> dict[str, Any]:
    """POST a JSON body and return the parsed JSON response."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers,
                                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _ollama_json(spec: ModelSpec, system: str, user: str) -> tuple[dict[str, Any], int, int]:
    """Call an Ollama model in JSON mode via /api/chat."""
    out = _post_json(
        (spec.endpoint or "").rstrip("/") + "/api/chat",
        {"model": spec.name, "format": "json", "stream": False,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {},
    )
    data = json.loads(out["message"]["content"])
    return data, int(out.get("prompt_eval_count", 0)), int(out.get("eval_count", 0))


def _openai_json(
    spec: ModelSpec, system: str, user: str, key: str | None
) -> tuple[dict[str, Any], int, int]:
    """Call any OpenAI-compatible endpoint via /chat/completions (JSON mode)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    out = _post_json(
        (spec.endpoint or "").rstrip("/") + "/chat/completions",
        {"model": spec.name, "response_format": {"type": "json_object"},
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        headers,
    )
    data = json.loads(out["choices"][0]["message"]["content"])
    usage = out.get("usage", {})
    return data, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def complete_json(
    broker: Broker, tier: Tier, system: str, user: str, schema: dict[str, Any]
) -> dict[str, Any]:
    """Run a structured-JSON completion at the given tier via the Broker.

    Args:
        broker: Model broker (selection + budget + secrets).
        tier: Requested capability tier.
        system: System prompt.
        user: User prompt.
        schema: JSON schema the output must satisfy (enforced on Anthropic;
            requested via JSON mode elsewhere).

    Returns:
        The parsed JSON object the model produced.
    """
    spec = broker.choose(tier)
    key = broker.secrets.get(spec.api_key_ref) if spec.api_key_ref else None
    if spec.provider == "anthropic":
        data, in_tok, out_tok = _anthropic_json(spec, system, user, schema, key)
    elif spec.provider == "ollama":
        data, in_tok, out_tok = _ollama_json(spec, system, user)
    else:
        data, in_tok, out_tok = _openai_json(spec, system, user, key)
    broker.charge(tier, in_tok + out_tok)
    logger.info("complete tier=%s provider=%s model=%s tokens=%d", tier,
                spec.provider, spec.name, in_tok + out_tok)
    return data
