#!/usr/bin/env python3
"""
Raven — Contribute Init (SessionStart hook).

Caches the developer's git identity to .raven/state/.session-identity so the
PostToolUse hook (edit-tracker.py) doesn't have to spawn a subprocess per edit
(NFR-1: <5 ms p99). Also spawns the edit-watcher.py daemon if not running.

Never blocks. Never raises. Stdlib only.
"""

import json, os, subprocess, sys
from pathlib import Path

_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
STATE_DIR = _PROJECT / ".raven" / "state"
IDENTITY = STATE_DIR / ".session-identity"
WATCHER_PID = STATE_DIR / "edit-watcher.pid"
WATCHER_SCRIPT = Path(os.environ.get("HOME", str(Path.home()))) / ".claude" / "scripts" / "edit-watcher.py"


def git_email() -> str:
    try:
        out = subprocess.check_output(
            ["git", "config", "user.email"], stderr=subprocess.DEVNULL, timeout=2
        )
        return out.decode().strip()
    except Exception:
        return os.environ.get("GIT_AUTHOR_EMAIL", os.environ.get("USER", "unknown"))


def cache_identity() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "human": git_email(),
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
        "model": os.environ.get("CLAUDE_MODEL", ""),
        "mode": os.environ.get("CLAUDE_MODE", "default"),
        "skill": os.environ.get("CLAUDE_SKILL", ""),
    }
    try:
        IDENTITY.write_text(json.dumps(payload))
    except Exception:
        pass


def watcher_running() -> bool:
    if not WATCHER_PID.exists():
        return False
    try:
        pid = int(WATCHER_PID.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def spawn_watcher() -> None:
    if not WATCHER_SCRIPT.exists():
        return
    if watcher_running():
        return
    try:
        proc = subprocess.Popen(
            [sys.executable, str(WATCHER_SCRIPT), "--daemonize"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        WATCHER_PID.write_text(str(proc.pid))
    except Exception:
        pass


def main() -> None:
    try:
        cache_identity()
        spawn_watcher()
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
