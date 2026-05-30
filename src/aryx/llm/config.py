"""LLM configuration — env defaults plus an in-memory runtime override.

V1 reads ARYX_LLM_* from the environment (.env). A runtime override lets the
Settings UI switch provider/model/key without a redeploy. V2 will source the
override from AWS SSM/Secrets Manager instead of process memory.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LlmConfig:
    """Effective model configuration for one request cycle."""

    base_url: str
    menial_model: str
    reason_model: str
    provider: str = "ollama"
    cloud_model: str = ""
    cloud_api_key: str = ""
    timeout: int = 120


def _from_env() -> LlmConfig:
    return LlmConfig(
        base_url=os.environ.get("ARYX_LLM_BASE_URL", "http://localhost:11434").rstrip("/"),
        menial_model=os.environ.get("ARYX_LLM_MENIAL_MODEL", "qwen3.5:0.8b"),
        reason_model=os.environ.get("ARYX_LLM_REASON_MODEL", "lfm2.5-thinking"),
        provider=os.environ.get("ARYX_LLM_PROVIDER", "ollama"),
        cloud_model=os.environ.get("ARYX_LLM_CLOUD_MODEL", ""),
        cloud_api_key=os.environ.get("ARYX_LLM_CLOUD_KEY", ""),
        timeout=int(os.environ.get("ARYX_LLM_TIMEOUT", "120")),
    )


_override: dict[str, str] = {}


def set_override(**fields: str) -> None:
    """Merge non-empty runtime fields (provider/model/key) into the override."""
    for key, value in fields.items():
        if value:
            _override[key] = value


def clear_override() -> None:
    """Drop all runtime overrides, reverting to environment defaults."""
    _override.clear()


def effective() -> LlmConfig:
    """Return env config with any runtime override applied on top."""
    cfg = _from_env()
    if _override:
        cfg = replace(cfg, **{k: v for k, v in _override.items() if hasattr(cfg, k)})
    return cfg


def status() -> dict[str, object]:
    """Non-secret view of current config for display (key presence only)."""
    cfg = effective()
    return {
        "provider": cfg.provider,
        "base_url": cfg.base_url,
        "menial_model": cfg.menial_model,
        "reason_model": cfg.reason_model,
        "cloud_model": cfg.cloud_model,
        "cloud_key_set": bool(cfg.cloud_api_key),
    }
