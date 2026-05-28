"""Model roll-call: discover what each provider offers."""
from __future__ import annotations

import json
import logging
import urllib.request

from aryx.broker.specs import ModelSpec, Tier

logger = logging.getLogger(__name__)


def anthropic_catalog() -> list[ModelSpec]:
    """Return the known Claude models by tier (static, no network call)."""
    return [
        ModelSpec(name="claude-opus-4-7", provider="anthropic", tier="frontier",
                  context_tokens=1_000_000),
        ModelSpec(name="claude-sonnet-4-6", provider="anthropic", tier="mid",
                  context_tokens=1_000_000),
        ModelSpec(name="claude-haiku-4-5", provider="anthropic", tier="cheap",
                  context_tokens=200_000),
    ]


def discover_ollama(host: str, timeout: float = 5.0) -> list[ModelSpec]:
    """List models on an Ollama instance (local or hosted) via GET /api/tags.

    Args:
        host: Base URL of the instance, e.g. http://localhost:11434.
        timeout: Request timeout in seconds.

    Returns:
        One local-tier ModelSpec per installed Ollama model.
    """
    url = host.rstrip("/") + "/api/tags"
    # Host is user-configured at setup time; not attacker-controlled input.
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    models = [
        ModelSpec(name=m["name"], provider="ollama", tier="local", local=True,
                  endpoint=host.rstrip("/"))
        for m in payload.get("models", [])
    ]
    logger.info("ollama discovery host=%s models=%d", host, len(models))
    return models


def discover_openai_compatible(
    base_url: str,
    provider: str,
    tier: Tier = "mid",
    api_key: str | None = None,
    api_key_ref: str | None = None,
    timeout: float = 10.0,
) -> list[ModelSpec]:
    """List models from any OpenAI-compatible endpoint via GET /models.

    Works for xAI (Grok), Google (Gemini OpenAI-compat), OpenRouter, vLLM,
    LM Studio, etc. Discovered models get the given default tier (re-tier as
    needed). The base URL keeps the manifest's OpenAI-URL block intact.

    Args:
        base_url: API base, e.g. https://api.x.ai/v1.
        provider: Label stored on the spec, e.g. 'xai' or 'google'.
        tier: Default tier assigned to discovered models.
        api_key: Bearer key for the discovery call (optional for some servers).
        api_key_ref: Secret reference stored on each spec for later calls.
        timeout: Request timeout in seconds.

    Returns:
        One ModelSpec per advertised model.
    """
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    req = urllib.request.Request(base + "/models", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    models = [
        ModelSpec(name=m["id"], provider=provider, tier=tier, endpoint=base,
                  api_key_ref=api_key_ref)
        for m in payload.get("data", [])
    ]
    logger.info("openai-compatible discovery provider=%s models=%d", provider, len(models))
    return models
