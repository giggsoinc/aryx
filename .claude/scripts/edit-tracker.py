#!/usr/bin/env python3
"""
Raven — Edit Tracker (PostToolUse hook).

Captures Edit / Write / MultiEdit / NotebookEdit tool calls and appends one
JSONL record per call to .raven/state/edits.jsonl. Used by the Line
Attribution Engine to answer "who wrote this line, what model produced it."

Coexists with loc-tracker.py — different sink, different purpose.
Never blocks. Never raises. Stdlib only.
"""

import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
EDITS_PATH = _PROJECT / ".raven" / "state" / "edits.jsonl"
IDENTITY_CACHE = _PROJECT / ".raven" / "state" / ".session-identity"

SKIP_DIRS = {
    ".git", "node_modules", ".raven", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", "out", ".next", ".nuxt", ".cache",
    "vendor", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "coverage", ".coverage", "htmlcov",
}
SKIP_SUFFIXES = (
    ".min.js", ".min.css", ".bundle.js", ".chunk.js", ".lock", ".log",
    ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".mp3", ".mp4", ".mov", ".webm", ".woff", ".woff2", ".ttf",
    ".eot", ".otf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".xz",
    ".sqlite", ".sqlite3", ".db", ".pyc", ".pyo", ".class", ".o", ".so",
    ".dll", ".exe",
)
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum",
}


def should_track(file_path: str) -> bool:
    if not file_path:
        return False
    p = Path(file_path)
    if p.name in SKIP_FILES or p.name.lower().endswith(SKIP_SUFFIXES):
        return False
    return not any(part in SKIP_DIRS for part in p.parts)


def line_ranges(tool: str, tin: dict) -> tuple:
    """Return (old_start, old_end, new_start, new_end). Best-effort, 1-indexed."""
    if tool == "Write":
        content = tin.get("content", "") or ""
        n = len(content.splitlines()) or (1 if content else 0)
        return (0, 0, 1, n)
    if tool == "Edit":
        old, new = tin.get("old_string", ""), tin.get("new_string", "")
        old_n = len(old.splitlines()) or (1 if old else 0)
        new_n = len(new.splitlines()) or (1 if new else 0)
        start = _find_line(tin.get("file_path", ""), old)
        return (start, start + max(old_n - 1, 0), start, start + max(new_n - 1, 0))
    if tool == "MultiEdit":
        edits = tin.get("edits", []) or []
        if not edits:
            return (0, 0, 0, 0)
        first = edits[0]
        last = edits[-1]
        start = _find_line(tin.get("file_path", ""), first.get("old_string", ""))
        new_total = sum(len((e.get("new_string") or "").splitlines()) for e in edits)
        return (start, start, start, start + max(new_total - 1, 0))
    if tool == "NotebookEdit":
        new = tin.get("new_source", "") or ""
        n = len(new.splitlines()) or (1 if new else 0)
        return (0, 0, 1, n)
    return (0, 0, 0, 0)


def _find_line(path: str, needle: str) -> int:
    if not path or not needle:
        return 1
    try:
        text = Path(path).read_text(errors="ignore")
    except Exception:
        return 1
    idx = text.find(needle)
    if idx < 0:
        return 1
    return text.count("\n", 0, idx) + 1


def session_ctx() -> dict:
    cached = {}
    try:
        if IDENTITY_CACHE.exists():
            cached = json.loads(IDENTITY_CACHE.read_text())
    except Exception:
        cached = {}
    return {
        "session_id": os.environ.get("CLAUDE_SESSION_ID", cached.get("session_id", "")),
        "model":      os.environ.get("CLAUDE_MODEL",      cached.get("model", "")),
        "mode":       os.environ.get("CLAUDE_MODE",       cached.get("mode", "default")),
        "skill":      os.environ.get("CLAUDE_SKILL",      cached.get("skill", "")),
        "human":      os.environ.get("GIT_AUTHOR_EMAIL",  cached.get("human", "")),
    }


def append(record: dict) -> None:
    EDITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EDITS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def main() -> None:
    try:
        if sys.stdin.isatty():
            sys.exit(0)
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)
    try:
        resp = data.get("tool_response", {}) or {}
        if resp.get("error"):
            sys.exit(0)
        tool = data.get("tool_name", "") or ""
        tin = data.get("tool_input", {}) or {}
        file_path = tin.get("file_path") or tin.get("notebook_path") or ""
        if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            sys.exit(0)
        if not should_track(file_path):
            sys.exit(0)
        os_, oe, ns, ne = line_ranges(tool, tin)
        ctx = session_ctx()
        append({
            "ts":         datetime.now(timezone.utc).isoformat(),
            "source":     "ai",
            "tool":       tool,
            "file":       file_path,
            "old_range":  [os_, oe],
            "new_range":  [ns, ne],
            **ctx,
        })
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
