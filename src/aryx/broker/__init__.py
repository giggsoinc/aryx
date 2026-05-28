"""Model Broker: roll-call, tier association, and token rationing.

Selection layer only — it decides which model serves a request and enforces
budgets (frontier dollars stay scarce; cheap/local run free). Actual model
invocation is the caller's job (Increment 4+).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from aryx.broker.discovery import anthropic_catalog, discover_ollama
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
    ) -> None:
        """Wire the broker to a registry, governor, and secret provider."""
        self._registry = registry
        self._governor = governor
        self.secrets = secrets or EnvSecretProvider()

    def add_ollama(self, host: str) -> int:
        """Discover and register an Ollama instance's models; return the count."""
        specs = discover_ollama(host)
        for spec in specs:
            self._registry.add(spec)
        return len(specs)

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


def default_broker() -> Broker:
    """Build a Broker seeded from catalog.json plus the Claude catalog."""
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    registry = Registry()
    for entry in data.get("models", []):
        registry.add(ModelSpec(**entry))
    for spec in anthropic_catalog():
        registry.add(spec)
    return Broker(registry, TokenGovernor(data.get("budgets", {})))
