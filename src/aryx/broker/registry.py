"""In-memory model registry, queryable by tier."""
from __future__ import annotations

from aryx.broker.specs import ModelSpec, Tier


class Registry:
    """Holds available ModelSpecs; replaces by name so re-adds are idempotent."""

    def __init__(self) -> None:
        """Start with an empty registry."""
        self._models: list[ModelSpec] = []

    def add(self, spec: ModelSpec) -> None:
        """Register a model, replacing any existing entry with the same name."""
        self._models = [m for m in self._models if m.name != spec.name]
        self._models.append(spec)

    def by_tier(self, tier: Tier) -> list[ModelSpec]:
        """Return all models serving the given tier."""
        return [m for m in self._models if m.tier == tier]

    def all(self) -> list[ModelSpec]:
        """Return every registered model."""
        return list(self._models)
