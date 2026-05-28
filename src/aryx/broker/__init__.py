"""Model Broker: roll-call, tier association, token rationing, and embeddings.

Provider-agnostic selection layer (Anthropic + Ollama + any OpenAI-compatible
endpoint). It decides which model serves a tier and enforces budgets; actual
chat invocation lives in aryx/llm.py. Embeddings run on a local model (free).
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

from aryx.broker.discovery import (
    anthropic_catalog,
    discover_ollama,
    discover_openai_compatible,
)
from aryx.broker.governor import TokenGovernor
from aryx.broker.registry import Registry
from aryx.broker.secrets import EnvSecretProvider, SecretProvider
from aryx.broker.specs import TIER_LADDER, ModelSpec, Tier

logger = logging.getLogger(__name__)

_CATALOG = Path(__file__).parent / "catalog.json"

__all__ = ["Broker", "default_broker", "ModelSpec", "Registry", "TokenGovernor"]


class Broker:
    """Chooses a model for a requested tier, honoring token budgets."""

    def __init__(
        self,
        registry: Registry,
        governor: TokenGovernor,
        secrets: SecretProvider | None = None,
        embed_config: dict[str, str] | None = None,
    ) -> None:
        """Wire the broker to a registry, governor, secrets, and embed config."""
        self._registry = registry
        self._governor = governor
        self.secrets = secrets or EnvSecretProvider()
        self._embed = embed_config or {}

    def add_ollama(self, host: str) -> int:
        """Discover and register an Ollama instance's models; return the count."""
        specs = discover_ollama(host)
        for spec in specs:
            self._registry.add(spec)
        return len(specs)

    def add_openai_endpoint(
        self, base_url: str, provider: str, tier: Tier = "mid",
        api_key_ref: str | None = None,
    ) -> int:
        """Discover + register models from an OpenAI-compatible endpoint.

        Covers Grok (xAI), Gemini, OpenRouter, vLLM, LM Studio, etc.
        """
        key = self.secrets.get(api_key_ref) if api_key_ref else None
        specs = discover_openai_compatible(
            base_url, provider, tier=tier, api_key=key, api_key_ref=api_key_ref
        )
        for spec in specs:
            self._registry.add(spec)
        return len(specs)

    def register(self, spec: ModelSpec) -> None:
        """Hand-register a single model (manual config path)."""
        self._registry.add(spec)

    def choose(self, tier: Tier) -> ModelSpec:
        """Pick a model for the tier, downgrading if its budget is spent."""
        effective = self._governor.effective_tier(tier)
        for candidate in TIER_LADDER[TIER_LADDER.index(effective):]:
            options = self._registry.by_tier(candidate)
            if options:
                return options[0]
        raise LookupError(f"no model available for tier '{tier}'")

    def charge(self, tier: Tier, tokens: int) -> None:
        """Record spend so subsequent choices can downgrade."""
        self._governor.charge(tier, tokens)

    def models(self) -> list[ModelSpec]:
        """Return every registered model (for the setup UI roll-call)."""
        return self._registry.all()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts on the configured local model (Ollama /api/embed).

        Returns an empty list if no embed model is configured, so callers can
        gracefully fall back to string-only similarity.
        """
        if not self._embed.get("model") or not self._embed.get("endpoint"):
            return []
        body = json.dumps({"model": self._embed["model"], "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            self._embed["endpoint"].rstrip("/") + "/api/embed",
            data=body, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("embeddings", [])


def default_broker() -> Broker:
    """Build a Broker seeded from catalog.json plus the Claude catalog."""
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    registry = Registry()
    for entry in data.get("models", []):
        registry.add(ModelSpec(**entry))
    for spec in anthropic_catalog():
        registry.add(spec)
    return Broker(registry, TokenGovernor(data.get("budgets", {})),
                  embed_config=data.get("embed", {}))
