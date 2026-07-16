#!/usr/bin/env python3
"""
Raven Enterprise — Session End hook
Decrements the daily session counter when the user exits via /exit so the Hub
dashboard reflects only sessions that the user explicitly started or resumed
(see session-start.py). If the +1 had already been streamed to Hub by
stream-signal.py for this day, we also POST a sessions=-1 delta so the Hub's
running total stays in sync.

Reasons we act on:
  - "prompt_input_exit"  — user typed /exit

All other end reasons (logout, clear, compact, other) are left alone.
"""

import json, os, sys, urllib.request, urllib.error
from pathlib import Path
from datetime import date

STATS_PATH    = Path(".raven/.cache/session-stats.json")
MANIFEST_PATH = Path(".raven/manifest.json")
SECRETS_PATH  = Path(".raven/manifest.secrets.json")
POLICY_PATH   = Path(".raven/mcp-policy.json")


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text()) if path.exists() else (default or {})
    except Exception:
        return default or {}


def post_decrement(hub_url: str, manifest: dict) -> bool:
    """POST a sessions=-1 delta so the Hub upsert subtracts one from today's count."""
    url = hub_url.rstrip("/") + "/api/v1/signals"
    # policy_mode is overwritten (not accumulated) on the Hub side, so we must
    # echo the live value rather than let Pydantic default it to "shadow".
    payload = {
        "date":        date.today().isoformat(),
        "user":        manifest.get("user_email") or os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("USER", "unknown"),
        "org":         manifest.get("org", ""),
        "project":     manifest.get("project", os.path.basename(os.getcwd())),
        "sessions":    -1,
        "policy_mode": load_json(POLICY_PATH).get("mode", "shadow"),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Raven-Agent": "enterprise-v1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False


def main():
    # Read hook stdin to learn why the session ended
    reason = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                reason = (json.loads(raw).get("reason") or "").lower()
    except Exception:
        pass

    # Only /exit triggers a decrement
    if reason != "prompt_input_exit":
        sys.exit(0)

    today = date.today().isoformat()
    stats = load_json(STATS_PATH, default={})
    if stats.get("date") != today or stats.get("sessions", 0) <= 0:
        sys.exit(0)  # nothing to decrement

    sent_before = stats.get("sessions_sent", 0)
    stats["sessions"] = stats["sessions"] - 1

    # If the +1 was already streamed to Hub, try to send a -1 delta so the Hub
    # running total stays consistent with local. Only advance sessions_sent on
    # confirmed POST success — otherwise leave it so the next stream-signal
    # run picks up the negative delta and retries.
    if sent_before > 0:
        manifest = load_json(MANIFEST_PATH)
        secrets  = load_json(SECRETS_PATH)
        hub_url  = manifest.get("hub_url") or secrets.get("hub_url", "")
        if hub_url and post_decrement(hub_url, manifest):
            stats["sessions_sent"] = sent_before - 1

    try:
        STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATS_PATH.write_text(json.dumps(stats))
    except Exception:
        pass


if __name__ == "__main__":
    main()
