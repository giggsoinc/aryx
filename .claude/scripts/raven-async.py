#!/usr/bin/env python3
"""
Raven — Async Hub Sync Worker.

Drains the contribute-queue. Polls every 300s. Batches up to 250 records per
POST. Exponential backoff via the queue helper. Never crashes the developer's
session.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

POLL_INTERVAL = float(os.environ.get("RAVEN_ASYNC_POLL_SECONDS", "300"))
HUB_URL = os.environ.get("HUB_URL", "").rstrip("/")
AGENT_KEY = os.environ.get("RAVEN_AGENT_KEY", "")
PROJECT_ID = os.environ.get("RAVEN_PROJECT_ID", "")
BATCH = int(os.environ.get("RAVEN_ASYNC_BATCH", "250"))


def _load_queue():
    spec = importlib.util.spec_from_file_location(
        "_q", Path(__file__).resolve().parent / "contribute-queue.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_KIND_PATHS = {
    "attributions": "/attributions",
    "signoffs":     "/signoffs",
    "corrections":  "/corrections",
}


def endpoint_for(kind: str, project_id: str) -> str:
    suffix = _KIND_PATHS.get(kind)
    if suffix is None:
        raise ValueError(f"unknown sync kind: {kind!r}")
    return f"{HUB_URL}/api/v1/projects/{project_id}{suffix}"


def post(url: str, body: dict, timeout: float = 10.0) -> int:
    if not url:
        return 0
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                  "X-Raven-Agent": AGENT_KEY} if AGENT_KEY else
                 {"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def drain_once(queue) -> tuple[int, int]:
    items = queue.pending(limit=BATCH)
    if not items:
        return (0, 0)
    by_kind: dict[tuple[str, str], list[dict]] = {}
    by_kind_ids: dict[tuple[str, str], list[int]] = {}
    for it in items:
        key = (it["kind"], it["project_id"])
        by_kind.setdefault(key, []).append(it["payload"])
        by_kind_ids.setdefault(key, []).append(it["id"])
    sent = 0
    failed = 0
    for (kind, pid), payloads in by_kind.items():
        ids = by_kind_ids[(kind, pid)]
        try:
            url = endpoint_for(kind, pid)
        except ValueError:
            # Unknown kind = permanent error — drop instead of retrying forever.
            queue.mark_done(ids)
            failed += len(ids)
            continue
        body = {kind: payloads}
        status = post(url, body)
        if 200 <= status < 300:
            queue.mark_done(ids)
            sent += len(ids)
        else:
            queue.mark_retry(ids)
            failed += len(ids)
    return (sent, failed)


def main() -> int:
    queue = _load_queue()
    if not HUB_URL:
        return 0
    while True:
        try:
            drain_once(queue)
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        q = _load_queue()
        sent, failed = drain_once(q)
        print(json.dumps({"sent": sent, "failed": failed}))
        sys.exit(0)
    main()
