"""Tier router — keeps thinking models off menial work.

menial: fast extraction/classification — local small model, thinking OFF.
reason: answer synthesis / multi-hop — reason model, thinking ON.
A configured cloud model overrides both tiers when a key is present.
"""
from __future__ import annotations

from typing import Literal

from aryx.llm.config import LlmConfig

Tier = Literal["menial", "reason"]


def pick(tier: Tier, cfg: LlmConfig) -> tuple[str, bool]:
    """Return (model, think) for a tier given the effective config."""
    if cfg.cloud_api_key and cfg.cloud_model and cfg.provider != "ollama":
        return cfg.cloud_model, False
    if tier == "menial":
        return cfg.menial_model, False
    return cfg.reason_model, True
