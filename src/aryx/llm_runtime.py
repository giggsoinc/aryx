"""Runtime-swappable LLM config for Ask.

The Settings panel can change provider/model/key live (no restart). Ask calls
chat(role, ...) and this module builds the right single-model Broker on the fly,
reusing aryx.llm's provider routing. V1 holds config in process memory; V2 will
source secrets from AWS via the existing AwsSecretProvider.
"""
from __future__ import annotations

import logging
import os

import psycopg

from aryx.broker import Broker, ModelSpec, Registry, TokenGovernor
from aryx.llm import complete_text
from aryx.queries import load

logger = logging.getLogger(__name__)

_KEY_REF = "ARYX_RUNTIME_KEY"

_state: dict[str, str] = {
    "provider": os.environ.get("ARYX_LLM_PROVIDER", "ollama"),
    "menial_model": os.environ.get("ARYX_LLM_MENIAL_MODEL", "qwen3.5:0.8b"),
    "answer_model": os.environ.get(
        "ARYX_LLM_REASON_MODEL", "lfm2.5-thinking:latest"),
    "endpoint": os.environ.get("ARYX_LLM_BASE_URL", "http://ollama:11434"),
    "api_key": os.environ.get("ARYX_LLM_API_KEY", ""),
}


class _RuntimeSecrets:
    """SecretProvider returning the key entered via the Settings panel."""

    def get(self, ref: str) -> str:
        return _state["api_key"]


def _broker_for(model: str) -> Broker:
    is_ollama = _state["provider"] == "ollama"
    registry = Registry()
    registry.add(ModelSpec(
        name=model, provider=_state["provider"], tier="cheap",
        local=is_ollama, endpoint=_state["endpoint"] or None,
        api_key_ref=None if is_ollama else _KEY_REF,
    ))
    return Broker(registry, TokenGovernor({}), secrets=_RuntimeSecrets())


def _log_call(role: str, model: str, pt: int, ct: int, ms: int, err: str) -> None:
    """Best-effort persist to aryx_llm_call (no-op if DB unavailable)."""
    dsn = os.environ.get("ARYX_RDB_DSN", "")
    if not dsn:
        return
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(load("insert_llm_call"),
                            (role, model, _state["provider"], pt, ct, ms, "ask", err or None))
    except Exception:  # noqa: BLE001
        logger.debug("llm call log write failed", exc_info=True)


def chat(role: str, system: str, user: str) -> tuple[str, int, int]:
    """Run a completion for 'menial' or 'answer' using the configured model."""
    model = _state["menial_model"] if role == "menial" else _state["answer_model"]
    import time
    start = time.monotonic()
    text, pt, ct = complete_text(_broker_for(model), "cheap", system, user, think=False)
    ms = int((time.monotonic() - start) * 1000)
    _log_call(role, model, pt, ct, ms, "")
    return text, pt, ct


def set_config(**fields: str) -> None:
    """Merge non-empty Settings fields into the live config."""
    for key in ("provider", "menial_model", "answer_model", "endpoint", "api_key"):
        if fields.get(key):
            _state[key] = fields[key]


def status() -> dict[str, object]:
    """Non-secret view of the current config (key presence only)."""
    return {
        "provider": _state["provider"],
        "menial_model": _state["menial_model"],
        "answer_model": _state["answer_model"],
        "endpoint": _state["endpoint"],
        "api_key_set": bool(_state["api_key"]),
    }
