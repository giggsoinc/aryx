"""Unified model completion: route a tiered request to the chosen provider.

The Broker decides which model serves a tier; this calls it. Anthropic uses
structured outputs; Ollama uses JSON mode. Token usage is charged back to the
governor so budgets actually bite.
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
    spec: ModelSpec, system: str, user: str, schema: dict[str, Any]
) -> tuple[dict[str, Any], int, int]:
    """Call an Anthropic model with structured JSON output."""
    import anthropic  # lazy: only on the Anthropic path

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=spec.name,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), resp.usage.input_tokens, resp.usage.output_tokens


def _ollama_json(spec: ModelSpec, system: str, user: str) -> tuple[dict[str, Any], int, int]:
    """Call an Ollama model in JSON mode via /api/chat."""
    body = json.dumps({
        "model": spec.name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": "json",
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        (spec.endpoint or "").rstrip("/") + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        out = json.loads(resp.read().decode("utf-8"))
    data = json.loads(out["message"]["content"])
    return data, int(out.get("prompt_eval_count", 0)), int(out.get("eval_count", 0))


def complete_json(
    broker: Broker, tier: Tier, system: str, user: str, schema: dict[str, Any]
) -> dict[str, Any]:
    """Run a structured-JSON completion at the given tier via the Broker.

    Args:
        broker: Model broker (selection + budget).
        tier: Requested capability tier.
        system: System prompt.
        user: User prompt.
        schema: JSON schema the output must satisfy.

    Returns:
        The parsed JSON object the model produced.
    """
    spec = broker.choose(tier)
    if spec.provider == "anthropic":
        data, in_tok, out_tok = _anthropic_json(spec, system, user, schema)
    else:
        data, in_tok, out_tok = _ollama_json(spec, system, user)
    broker.charge(tier, in_tok + out_tok)
    logger.info("complete tier=%s model=%s tokens=%d", tier, spec.name, in_tok + out_tok)
    return data
