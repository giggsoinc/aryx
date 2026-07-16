#!/usr/bin/env python3
"""
Raven — Edit Watcher (SessionStart daemon).

Detects file mutations that have no corresponding tool-call record within the
dedup window (default ±200 ms). Attributes such edits to the developer's
git identity. Pairs with edit-tracker.py to cover both AI and human edits.

watchdog is the only non-stdlib dep — if missing, this exits silently.
"""

import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
STATE_DIR = _PROJECT / ".raven" / "state"
EDITS_PATH = STATE_DIR / "edits.jsonl"
IDENTITY = STATE_DIR / ".session-identity"
DEDUP_MS = 200
TAIL_RECORDS = 40

SKIP_DIRS = {".git", ".raven", "node_modules", "__pycache__", ".venv",
             "venv", "dist", "build", "out", ".next", ".cache", "vendor",
             ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "coverage"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".log", ".lock", ".tmp", ".swp", ".swo",
                 ".db", ".sqlite", ".sqlite3", ".png", ".jpg", ".jpeg",
                 ".gif", ".pdf", ".zip", ".tar", ".gz")


def load_identity() -> str:
    try:
        return json.loads(IDENTITY.read_text()).get("human", "unknown")
    except Exception:
        return os.environ.get("GIT_AUTHOR_EMAIL", "unknown")


def tail_recent_ts(path: Path) -> list:
    """Return last TAIL_RECORDS timestamps from edits.jsonl (epoch seconds)."""
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 32768))
            chunk = f.read().decode("utf-8", errors="ignore")
        lines = [ln for ln in chunk.splitlines() if ln.strip()][-TAIL_RECORDS:]
        out = []
        for ln in lines:
            try:
                rec = json.loads(ln)
                ts = rec.get("ts", "")
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                out.append((rec.get("file", ""), dt.timestamp()))
            except Exception:
                continue
        return out
    except Exception:
        return []


def recently_tool_tracked(file_path: str) -> bool:
    now = time.time()
    for f, ts in tail_recent_ts(EDITS_PATH):
        if f == file_path and abs(now - ts) <= DEDUP_MS / 1000.0:
            return True
    return False


def should_watch(path: str) -> bool:
    p = Path(path)
    if any(part in SKIP_DIRS for part in p.parts):
        return False
    if p.name.lower().endswith(SKIP_SUFFIXES):
        return False
    return p.is_file() if p.exists() else True


def append_human(file_path: str, human: str, lines_now: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "human",
        "tool": "human-edit",
        "file": file_path,
        "old_range": [0, 0],
        "new_range": [1, lines_now],
        "model": "",
        "mode": "",
        "skill": "",
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
        "human": human,
    }
    with EDITS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def run() -> int:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception:
        return 0
    human = load_identity()

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            try:
                if event.is_directory:
                    return
                path = event.src_path
                if not should_watch(path):
                    return
                if recently_tool_tracked(path):
                    return
                try:
                    n = sum(1 for _ in Path(path).open("rb"))
                except Exception:
                    n = 0
                append_human(path, human, n)
            except Exception:
                pass

    obs = Observer()
    obs.schedule(Handler(), ".", recursive=True)
    obs.start()
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        obs.stop()
        obs.join(timeout=2)
    return 0


def main() -> None:
    if "--daemonize" in sys.argv:
        try:
            sys.exit(run())
        except Exception:
            sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
