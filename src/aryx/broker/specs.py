"""Model specs and tiers for the Broker."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["frontier", "mid", "cheap", "local"]

# Order used when a tier's budget is exhausted: downgrade left-to-right.
TIER_LADDER: tuple[Tier, ...] = ("frontier", "mid", "cheap", "local")


class ModelSpec(BaseModel):
    """One available model and the tier it serves.

    provider is open. Dispatch (see aryx/llm.py): 'anthropic' uses the Claude
    SDK, 'ollama' uses the native Ollama API, and ANY other value (e.g. 'xai',
    'google', 'openrouter', 'vllm', 'lmstudio') uses the OpenAI-compatible HTTP
    path against `endpoint` — so Phi-4, Gemini, Grok, etc. all plug in.
    """

    name: str = Field(description="Provider model id, e.g. 'grok-3', 'phi4'.")
    provider: str = Field(description="anthropic | ollama | any openai-compatible.")
    tier: Tier = Field(description="Capability/cost tier this model serves.")
    context_tokens: int = Field(default=0, description="Context window size.")
    local: bool = Field(default=False, description="True for self-hosted/local models.")
    endpoint: str | None = Field(
        default=None, description="Base URL (Ollama host or OpenAI-compatible base)."
    )
    api_key_ref: str | None = Field(
        default=None, description="Secret reference resolved via the SecretProvider."
    )
