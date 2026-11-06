"""raven-log emitter wiring for Aryx (repo-root config.py).

Every ``raven_log()`` call site imports ``from config import log as raven_log``
— never ``raven_logger.raven_log`` directly, because the SDK's own default
emitter only prints JSON to stdout and would never reach the configured sink.

Aryx must keep running with no logging sink configured, so this wrapper is
deliberately fail-safe:

* The S3 sink is configured purely from environment variables (no defaults,
  no credentials in code): ``RAVEN_LOG_S3_PATH`` (``s3://bucket/prefix/``),
  ``RAVEN_LOG_S3_ACCESS_ID``, ``RAVEN_LOG_S3_ACCESS_TOKEN`` and optionally
  ``RAVEN_LOG_S3_REGION``.
* The emitter is built lazily on first use, never at import time, so merely
  importing this module can't fail in an environment where they are unset.
* When the variables are unset, the optional ``raven-logger`` package is not
  installed (``pip install "raven-logger[s3]"``), or emitting raises, the
  record is written to the standard ``logging`` module instead. Logging must
  never break an ingest.
"""
from __future__ import annotations

import logging
import os
from typing import Any

_fallback = logging.getLogger("aryx.raven_log")
_LEVELS = {"ERROR": logging.ERROR, "WARN": logging.WARNING,
           "INFO": logging.INFO, "DEBUG": logging.DEBUG}

_emitter: Any = None
_emitter_tried = False


def _get_emitter() -> Any:
    """Build the S3 emitter once from env vars; None when not configured."""
    global _emitter, _emitter_tried
    if _emitter_tried:
        return _emitter
    _emitter_tried = True
    path = os.environ.get("RAVEN_LOG_S3_PATH", "")
    access_id = os.environ.get("RAVEN_LOG_S3_ACCESS_ID", "")
    token = os.environ.get("RAVEN_LOG_S3_ACCESS_TOKEN", "")
    if not (path and access_id and token):
        return None
    try:
        from raven_logger import S3Emitter
        _emitter = S3Emitter(
            s3_path=path, access_id=access_id, access_token=token,
            region_name=os.environ.get("RAVEN_LOG_S3_REGION", "us-east-1"))
    except Exception as exc:  # noqa: BLE001 — a bad sink must not break Aryx
        _fallback.warning("raven-log S3 emitter unavailable: %s", exc)
    return _emitter


def log(level: str, message: str, **kwargs: Any) -> None:
    """Emit one raven-log record; never raises.

    Goes to the S3 sink when configured, otherwise to stdlib ``logging``.
    """
    emitter = _get_emitter()
    if emitter is not None:
        try:
            from raven_logger import raven_log
            raven_log(level, message, _emit=emitter, **kwargs)
            return
        except Exception as exc:  # noqa: BLE001 — fall through to stdlib
            _fallback.warning("raven-log emit failed: %s", exc)
    _fallback.log(_LEVELS.get(level, logging.INFO), "%s %s",
                  message, kwargs.get("context") or {})
