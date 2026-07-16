#!/usr/bin/env python3
"""Hub-calling helpers for /raven-contribute (Sprint A4).

`audit` reads from the Hub directly (no offline mode — read requires live data).
`attribute` and `signoff` enqueue payloads via contribute-queue.py for the
raven-async worker to drain.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable


ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
HUB_URL = os.environ.get("HUB_URL", "").rstrip("/")
PROJECT_ID = os.environ.get("RAVEN_PROJECT_ID", "")
AGENT_KEY = os.environ.get("RAVEN_AGENT_KEY", "")


def _load_queue():
    qpath = ROOT / "agent/scripts/contribute-queue.py"
    if not qpath.exists():
        return None
    spec = importlib.util.spec_from_file_location("_q", qpath)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _http_get(path: str, params: dict) -> list | dict | None:
    if not HUB_URL:
        return None
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{HUB_URL}{path}" + (f"?{q}" if q else "")
    req = urllib.request.Request(url, method="GET")
    if AGENT_KEY:
        req.add_header("X-Raven-Agent", AGENT_KEY)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None


def audit(args: list[str]) -> int:
    """audit --model X --since ISO --until ISO [--csv]"""
    flags: dict = {}
    want_csv = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--csv":
            want_csv = True
        elif a.startswith("--") and i + 1 < len(args):
            flags[a[2:]] = args[i + 1]
            i += 1
        i += 1
    if not PROJECT_ID:
        print("RAVEN_PROJECT_ID not set", file=sys.stderr)
        return 2
    rows = _http_get(f"/api/v1/projects/{PROJECT_ID}/audit", flags)
    if rows is None:
        print("Hub unreachable", file=sys.stderr)
        return 1
    if want_csv:
        w = csv.writer(sys.stdout)
        w.writerow(["path", "start", "end", "human", "model", "ts", "commit"])
        for r in rows:
            w.writerow([r.get("path"), r.get("start"), r.get("end"),
                        r.get("human"), r.get("model"), r.get("ts"),
                        r.get("commit")])
    else:
        for r in rows:
            print(f"  {r.get('path')}:{r.get('start')}-{r.get('end')}  "
                   f"human={r.get('human')}  model={r.get('model')}  "
                   f"ts={r.get('ts')}")
    return 0


def attribute(args: list[str]) -> int:
    """attribute <file>:<a>-<b> <email>"""
    if len(args) < 2 or ":" not in args[0]:
        print("usage: attribute <file>:<a>-<b> <email>", file=sys.stderr)
        return 2
    file, rng = args[0].rsplit(":", 1)
    a_s, b_s = rng.split("-")
    a, b = int(a_s), int(b_s)
    email = args[1]
    q = _load_queue()
    if q is None:
        print("contribute-queue.py not found", file=sys.stderr)
        return 1
    q.enqueue("corrections", PROJECT_ID or "local", {
        "file_path": file, "start_line": a, "end_line": b,
        "human_email": email, "reason": "manual correction via CLI",
    })
    print(f"enqueued correction: {file}:{a}-{b} → {email}")
    return 0


def signoff(args: list[str]) -> int:
    """signoff <file>"""
    if not args:
        print("usage: signoff <file>", file=sys.stderr)
        return 2
    file = args[0]
    q = _load_queue()
    if q is None:
        return 1
    import subprocess
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        email = subprocess.check_output(
            ["git", "config", "user.email"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        sha = "unknown"
        email = os.environ.get("GIT_AUTHOR_EMAIL", "unknown")
    q.enqueue("signoffs", PROJECT_ID or "local",
              {"file_path": file, "commit_sha": sha, "signer_email": email})
    print(f"enqueued signoff: {file}  {email}@{sha[:8]}")
    return 0
