"""Model specs and tiers for the Broker."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["frontier", "mid", "cheap", "local"]

# Order used when a tier's budget is exhausted: downgrade left-to-right.
TIER_LADDER: tuple[Tier, ...] = ("frontier", "mid", "cheap", "local")


class ModelSpec(BaseModel):
    """One available model and the tier it serves."""

    name: str = Field(description="Provider model id, e.g. 'claude-opus-4-7'.")
    provider: Literal["anthropic", "ollama"] = Field(description="Backend provider.")
    tier: Tier = Field(description="Capability/cost tier this model serves.")
    context_tokens: int = Field(default=0, description="Context window size.")
    local: bool = Field(default=False, description="True for self-hosted/local models.")
