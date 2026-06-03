"""Audit log writer — JSONL per Raven discipline.

Every meaningful user/system action writes one row to
`.raven/audit/YYYY-MM-DD.log`. Format is JSON Lines, one event per line, so
ops can grep, ship to S3, or replay without parsing a custom format.

The writer is best-effort: if the audit directory is read-only or missing
the parent, it logs the failure and returns; it never raises into the
caller, so user-visible actions stay responsive.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUDIT_DIR_ENV = "ARYX_AUDIT_DIR"
_DEFAULT_DIR = Path(".raven/audit")


def _audit_dir() -> Path:
    """Return the configured audit directory, creating it on demand."""
    raw = os.environ.get(_AUDIT_DIR_ENV) or str(_DEFAULT_DIR)
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit dir create failed path=%s err=%s", path, exc)
    return path


def _now_utc() -> str:
    """ISO-8601 timestamp in UTC, second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(stage: str, action: str, actor: str = "system",
        workspace_id: int | None = None,
        target: str = "", outcome: str = "ok",
        **extra: Any) -> None:
    """Append a single audit event to today's log file.

    Args:
        stage: Lifecycle stage — Brief / Ingest / Lightweight / HITL /
            Heavyweight / Publish / Ask / Pipeline.
        action: Specific action — approve_type, add_rule, snapshot,
            ingest_start, ingest_complete, publish_export, ask, etc.
        actor: Who triggered it. "system" for pipeline events;
            workspace context.roles or a user id for human events.
        workspace_id: Workspace scope, when applicable.
        target: Object the action affected (entity name, rule name, etc.).
        outcome: "ok" | "blocked" | "error" | "skipped".
        **extra: Free-form payload merged into the event.
    """
    event: dict[str, Any] = {
        "ts": _now_utc(),
        "stage": stage,
        "action": action,
        "actor": actor,
        "workspace_id": workspace_id,
        "target": target,
        "outcome": outcome,
    }
    if extra:
        event["extra"] = extra
    path = _audit_dir() / f"{datetime.now(timezone.utc):%Y-%m-%d}.log"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit write failed path=%s err=%s", path, exc)
