"""Per-provider JSON completion paths — Anthropic / Ollama / OpenAI-compatible.

Split out of aryx.llm so each module stays under the 150-line budget.
_post_json includes 429 retry-with-backoff so callers transparently
recover from Gemini/OpenAI free-tier throttling.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from aryx.broker.specs import ModelSpec

logger = logging.getLogger(__name__)

# Per-call LLM timeout. Default 120s — long enough for a slow local model,
# short enough that one frozen call recovers instead of wedging the job for
# 10 minutes. Override with ARYX_LLM_TIMEOUT.
_DEFAULT_TIMEOUT = float(os.environ.get("ARYX_LLM_TIMEOUT", "120"))


def post_json(url: str, body: dict[str, Any], headers: dict[str, str],
              timeout: float | None = None) -> dict[str, Any]:
    """POST a JSON body and return the parsed JSON response.

    Retries on HTTP 429 (rate-limit) with exponential backoff capped at
    ~60s total wait so a single chunk doesn't stall the whole pipeline.
    """
    if timeout is None:
        timeout = _DEFAULT_TIMEOUT
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers,
                                 "Content-Type": "application/json"})
    delay = 2.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 4:
                logger.warning("429 throttled — sleep %.1fs then retry (%d/5)",
                               delay, attempt + 2)
                time.sleep(delay)
                delay = min(delay * 2, 16.0)
                continue
            # Surface the provider's real error instead of a bare HTTP code.
            # Gemini/OpenAI return an explanatory JSON body (e.g. a blocked key
            # shows 403 API_KEY_SERVICE_BLOCKED, masked as 500 by the OpenAI
            # shim) — without this the caller only sees "HTTP Error 500" and
            # can't tell a key/permission problem from a server crash.
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "ignore").strip()
            except Exception:  # noqa: BLE001 — best-effort body read
                pass
            raise RuntimeError(
                f"LLM provider error: HTTP {exc.code} from {url}"
                + (f" — {detail[:500]}" if detail else f" ({exc.reason})")
            ) from exc
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


def _loads_lenient(content: str) -> dict[str, Any]:
    """Parse a model's JSON response, salvaging malformed/truncated output.

    Local models occasionally emit invalid JSON (a trailing comma, a cut-off
    object at num_predict). A bare json.loads would raise and surface as a 500
    to the caller. Try a strict parse, then the outermost {...} substring, and
    finally fall back to an empty dict so the pipeline degrades gracefully.
    """
    if not content:
        return {}
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = content.find("{"), content.rfind("}")
    if 0 <= start < end:
        try:
            parsed = json.loads(content[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            pass
    logger.warning("ollama_json: unparseable model output (%d chars), using {}",
                   len(content))
    return {}


def ollama_json(spec: ModelSpec, system: str,
                user: str) -> tuple[dict[str, Any], int, int]:
    """Call an Ollama model in JSON mode via /api/chat."""
    out = post_json(
        (spec.endpoint or "").rstrip("/") + "/api/chat",
        # think=False: JSON extraction never needs chain-of-thought. On
        # hybrid "thinking" models (e.g. lfm2.5-thinking) the reasoning phase
        # adds ~70s/call for no gain since format=json already constrains
        # output — it only risks wrapping the JSON in prose. Ignored by
        # non-thinking models, so it's safe across the tier ladder.
        {"model": spec.name, "format": "json", "stream": False,
         "think": False,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]},
        {},
    )
    data = _loads_lenient(out.get("message", {}).get("content", ""))
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
