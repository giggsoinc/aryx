"""Cloud document embeddings, so a Gemini deployment needs no Ollama.

Document chunks are embedded with the same provider that serves the LLM when
that provider has an OpenAI-compatible ``/embeddings`` endpoint (Gemini). The
vectors are asked for at the database column width (768), so no schema change
is needed. Ollama stays the default for local / Ollama deployments, and an
explicit ``ARYX_EMBED_ENDPOINT`` always wins.
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# provider label -> embedding model on that provider's OpenAI-compatible API
CLOUD_EMBED_MODELS = {"google": "gemini-embedding-001",
                      "gemini": "gemini-embedding-001"}
_BATCH = 100                       # inputs per request
_RETRY_STATUS = {429, 500, 502, 503, 504}
_ATTEMPTS = 3
_sleep = time.sleep                # replaced in tests


def cloud_embed_config(
    provider: str, endpoint: str, api_key_ref: str | None, dimensions: int,
    model_override: str = "",
) -> dict | None:
    """Embed settings for a cloud provider, or None to keep the Ollama path."""
    model = model_override or CLOUD_EMBED_MODELS.get(provider.lower(), "")
    if not model or not endpoint or not api_key_ref:
        return None
    return {"model": model, "endpoint": endpoint.rstrip("/"),
            "api_key_ref": api_key_ref, "dimensions": dimensions}


def _post(url: str, key: str, body: dict) -> dict:
    """POST JSON with retries on rate-limit / transient server errors."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRY_STATUS or attempt == _ATTEMPTS:
                raise RuntimeError(
                    f"embedding request failed: HTTP {exc.code} from {url}") from None
            logger.warning("embedding HTTP %s, retry %d/%d", exc.code, attempt, _ATTEMPTS)
            _sleep(attempt)
    raise RuntimeError("unreachable")  # pragma: no cover


def _unit(vector: list[float]) -> list[float]:
    """L2-normalise a vector. Gemini returns shortened (``dimensions``) embeddings that
    are not unit length; cosine search does not care, inner product and L2 do."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm > 0 else list(vector)


def embed_openai_compatible(config: dict, key: str, texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` via ``{endpoint}/embeddings``; one vector per text, in order."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH):
        batch = texts[start:start + _BATCH]
        payload = _post(
            config["endpoint"] + "/embeddings", key,
            {"model": config["model"], "input": batch,
             "dimensions": config["dimensions"]})
        rows = sorted(payload.get("data", []), key=lambda r: r.get("index", 0))
        if len(rows) != len(batch):
            raise RuntimeError(
                f"embedding response had {len(rows)} vectors for {len(batch)} inputs")
        vectors.extend(_unit(r["embedding"]) for r in rows)
    return vectors
