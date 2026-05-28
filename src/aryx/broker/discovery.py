"""Model roll-call: discover what each provider offers."""
from __future__ import annotations

import json
import logging
import urllib.request

from aryx.broker.specs import ModelSpec

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
        ModelSpec(name=m["name"], provider="ollama", tier="local", local=True)
        for m in payload.get("models", [])
    ]
    logger.info("ollama discovery host=%s models=%d", host, len(models))
    return models
