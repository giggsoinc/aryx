#!/usr/bin/env python3
"""
Raven — Contribute Sync Queue (agent-side).

Append-only SQLite queue at .raven/state/sync-queue.db. Records payloads
destined for the Hub (attributions batch, signoffs batch, corrections).

Importable library. The raven-async worker drains the queue.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable

QUEUE_PATH = Path(".raven/state/sync-queue.db")
DDL = """
CREATE TABLE IF NOT EXISTS pending (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kind             TEXT    NOT NULL,
    project_id       TEXT    NOT NULL,
    payload          TEXT    NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  REAL    NOT NULL DEFAULT 0,
    enqueued_at      REAL    NOT NULL,
    completed_at     REAL    NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_kind ON pending(kind, completed_at);
CREATE INDEX IF NOT EXISTS idx_pending_next ON pending(next_attempt_at)
    WHERE completed_at IS NULL;
"""


def _conn() -> sqlite3.Connection:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(QUEUE_PATH))
    c.executescript(DDL)
    return c


def enqueue(kind: str, project_id: str, payload: dict) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO pending (kind, project_id, payload, enqueued_at) "
            "VALUES (?, ?, ?, ?)",
            (kind, project_id, json.dumps(payload), time.time()),
        )
        return cur.lastrowid


def pending(limit: int = 250, now: float | None = None) -> list[dict]:
    now = now or time.time()
    with _conn() as c:
        rows = c.execute(
            "SELECT id, kind, project_id, payload, attempts "
            "FROM pending WHERE completed_at IS NULL AND next_attempt_at <= ? "
            "ORDER BY id ASC LIMIT ?", (now, limit)
        ).fetchall()
    out = []
    for rid, kind, pid, payload, attempts in rows:
        try:
            data = json.loads(payload)
        except Exception:
            data = {}
        out.append({"id": rid, "kind": kind, "project_id": pid,
                    "payload": data, "attempts": attempts})
    return out


def mark_done(ids: Iterable[int]) -> None:
    ids = list(ids)
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    with _conn() as c:
        c.execute(
            f"UPDATE pending SET completed_at = ? WHERE id IN ({placeholders})",
            (time.time(), *ids),
        )


def backoff_delay(attempts: int) -> float:
    """Exponential backoff: 1m, 5m, 30m, 2h, 6h (capped)."""
    schedule = (60, 300, 1800, 7200, 21600)
    return schedule[min(attempts, len(schedule) - 1)]


def mark_retry(ids: Iterable[int]) -> None:
    with _conn() as c:
        for rid in ids:
            row = c.execute(
                "SELECT attempts FROM pending WHERE id = ?", (rid,)
            ).fetchone()
            attempts = (row[0] if row else 0) + 1
            c.execute(
                "UPDATE pending SET attempts = ?, next_attempt_at = ? WHERE id = ?",
                (attempts, time.time() + backoff_delay(attempts), rid),
            )


def stats() -> dict:
    with _conn() as c:
        rows = c.execute(
            "SELECT kind, "
            "  SUM(CASE WHEN completed_at IS NULL THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) "
            "FROM pending GROUP BY kind"
        ).fetchall()
    return {k: {"pending": int(p or 0), "done": int(d or 0)} for k, p, d in rows}
