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

# True once the user has explicitly chosen/confirmed a model (persisted row).
_confirmed = False
_loaded = False


def _dsn() -> str:
    try:
        from aryx.config import get_settings
        return get_settings().rdb_dsn
    except Exception:  # noqa: BLE001
        return os.environ.get("ARYX_RDB_DSN", "")


def _ensure_loaded() -> None:
    """Overlay the persisted choice (if any) on env defaults, once.

    Precedence: user's persisted UI choice > env (.env) > Ollama defaults.
    Fail-soft — with no DB the env defaults simply stand.
    """
    global _loaded, _confirmed
    if _loaded:
        return
    _loaded = True
    dsn = _dsn()
    if not dsn:
        return
    try:
        with psycopg.connect(dsn, autocommit=True,
                             connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(load("select_llm_config"))
                row = cur.fetchone()
        if row:
            _state.update({"provider": row[0], "menial_model": row[1],
                           "answer_model": row[2], "endpoint": row[3],
                           "api_key": row[4] or _state["api_key"]})
            _confirmed = True
            logger.info("llm config restored: %s · %s",
                        row[0], row[2])
    except Exception:  # noqa: BLE001 — table may not exist yet
        logger.debug("llm config load skipped", exc_info=True)


class _RuntimeSecrets:
    """SecretProvider returning the key entered via the Settings panel."""

    def get(self, ref: str) -> str:
        return _state["api_key"]


def _broker_for(model: str) -> Broker:
    _ensure_loaded()
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
    """Merge non-empty Settings fields into the live config AND persist.

    Persisting marks the choice as confirmed — the Home gate goes away and
    container restarts keep the user's model instead of reverting to env.
    """
    global _confirmed
    _ensure_loaded()
    for key in ("provider", "menial_model", "answer_model", "endpoint", "api_key"):
        if fields.get(key):
            _state[key] = fields[key]
    dsn = _dsn()
    if dsn:
        try:
            with psycopg.connect(dsn, autocommit=True,
                                 connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute(load("upsert_llm_config"),
                                (_state["provider"], _state["menial_model"],
                                 _state["answer_model"], _state["endpoint"],
                                 _state["api_key"]))
            _confirmed = True
        except Exception:  # noqa: BLE001 — live config still applies
            logger.warning("llm config persist failed", exc_info=True)


def status() -> dict[str, object]:
    """Non-secret view of the current config (key presence only)."""
    _ensure_loaded()
    return {
        "provider": _state["provider"],
        "menial_model": _state["menial_model"],
        "answer_model": _state["answer_model"],
        "endpoint": _state["endpoint"],
        "api_key_set": bool(_state["api_key"]),
        "confirmed": _confirmed,
    }
