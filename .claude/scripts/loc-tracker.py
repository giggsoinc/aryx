#!/usr/bin/env python3
"""
Raven Enterprise — Lines-of-Code Tracker
PostToolUse hook for Write / Edit / MultiEdit / NotebookEdit.

Counts non-blank source lines Claude authored in the tool call and appends a
`model_call` event to .raven/.cache/signal-queue.json. stream-signal.py
aggregates these into the daily Hub signal under `lines_generated` /
`lines_accepted`, which the dashboard surfaces as "Lines of Code".

Never blocks. Never errors out.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
SIGNAL_QUEUE_PATH = _PROJECT / ".raven" / ".cache" / "signal-queue.json"

SKIP_DIRS = {
    ".git", "node_modules", ".raven", "__pycache__",
    ".venv", "venv", "env", ".env",
    "dist", "build", "out", ".next", ".nuxt",
    ".cache", "vendor",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "coverage", ".coverage", "htmlcov",
}
SKIP_SUFFIXES = (
    ".min.js", ".min.css", ".bundle.js", ".chunk.js",
    ".lock", ".log", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".mp3", ".mp4", ".mov", ".webm",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".xz",
    ".sqlite", ".sqlite3", ".db",
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe",
)
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "composer.lock",
    "Gemfile.lock", "go.sum",
}


def should_count(file_path: str) -> bool:
    if not file_path:
        return False
    p = Path(file_path)
    if p.name in SKIP_FILES:
        return False
    if p.name.lower().endswith(SKIP_SUFFIXES):
        return False
    for part in p.parts:
        if part in SKIP_DIRS:
            return False
    return True


def code_lines(text: str) -> int:
    """Count non-blank lines. Conservative definition of 'lines of code'."""
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def count_for(tool_name: str, tool_input: dict) -> int:
    """Net new non-blank source lines authored by this tool call."""
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not should_count(file_path):
        return 0

    if tool_name == "Write":
        # `content` is the new full file body. Old content isn't in the hook
        # payload, so for overwrites this counts the full new body — accurate
        # for the common case (new file) and an upper bound for rewrites.
        return code_lines(tool_input.get("content", ""))

    if tool_name == "Edit":
        new_n = code_lines(tool_input.get("new_string", ""))
        old_n = code_lines(tool_input.get("old_string", ""))
        return max(0, new_n - old_n)

    if tool_name == "MultiEdit":
        total = 0
        for edit in tool_input.get("edits", []) or []:
            new_n = code_lines(edit.get("new_string", ""))
            old_n = code_lines(edit.get("old_string", ""))
            total += max(0, new_n - old_n)
        return total

    if tool_name == "NotebookEdit":
        new_n = code_lines(tool_input.get("new_source", ""))
        old_n = code_lines(tool_input.get("old_source", ""))
        return max(0, new_n - old_n) if old_n else new_n

    return 0


def queue_event(lines: int):
    if lines <= 0:
        return
    SIGNAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue = []
    if SIGNAL_QUEUE_PATH.exists():
        try:
            queue = json.loads(SIGNAL_QUEUE_PATH.read_text()) or []
            if not isinstance(queue, list):
                queue = []
        except Exception:
            queue = []
    queue.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "model_call",
        "lines_generated": lines,
        "lines_accepted":  lines,
    })
    try:
        SIGNAL_QUEUE_PATH.write_text(json.dumps(queue))
    except Exception:
        pass


def main():
    try:
        if sys.stdin.isatty():
            sys.exit(0)
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)

    resp = data.get("tool_response", {}) or {}
    if resp.get("error"):
        sys.exit(0)

    try:
        n = count_for(data.get("tool_name", ""), data.get("tool_input", {}) or {})
        queue_event(n)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
