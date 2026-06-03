"""Per-provider JSON completion paths — Anthropic / Ollama / OpenAI-compatible.

Split out of aryx.llm so each module stays under the 150-line budget.
_post_json includes 429 retry-with-backoff so callers transparently
recover from Gemini/OpenAI free-tier throttling.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from aryx.broker.specs import ModelSpec

logger = logging.getLogger(__name__)


def post_json(url: str, body: dict[str, Any], headers: dict[str, str],
              timeout: float = 600.0) -> dict[str, Any]:
    """POST a JSON body and return the parsed JSON response.

    Retries on HTTP 429 (rate-limit) with exponential backoff capped at
    ~60s total wait so a single chunk doesn't stall the whole pipeline.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers,
                                 "Content-Type": "application/json"})
    delay = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            logger.warning("429 throttled — sleep %.1fs then retry (%d/5)",
                           delay, attempt + 2)
            time.sleep(delay)
            delay = min(delay * 2, 16.0)
    raise RuntimeError("unreachable")


def anthropic_json(
    spec: ModelSpec, system: str, user: str, schema: dict[str, Any],
    key: str | None,
) -> tuple[dict[str, Any], int, int]:
    """Call a Claude model with structured JSON output."""
    import anthropic  # lazy: only on the Anthropic path

    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    resp = client.messages.create(
        model=spec.name, max_tokens=4096, system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), resp.usage.input_tokens, resp.usage.output_tokens


def ollama_json(spec: ModelSpec, system: str,
                user: str) -> tuple[dict[str, Any], int, int]:
    """Call an Ollama model in JSON mode via /api/chat."""
    out = post_json(
        (spec.endpoint or "").rstrip("/") + "/api/chat",
        {"model": spec.name, "format": "json", "stream": False,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {},
    )
    data = json.loads(out["message"]["content"])
    return data, int(out.get("prompt_eval_count", 0)), int(out.get("eval_count", 0))


def openai_json(
    spec: ModelSpec, system: str, user: str, key: str | None,
) -> tuple[dict[str, Any], int, int]:
    """Call any OpenAI-compatible endpoint via /chat/completions (JSON mode)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    out = post_json(
        (spec.endpoint or "").rstrip("/") + "/chat/completions",
        {"model": spec.name, "response_format": {"type": "json_object"},
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        headers,
    )
    data = json.loads(out["choices"][0]["message"]["content"])
    usage = out.get("usage", {})
    return data, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
