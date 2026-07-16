"""Damage-control audit emitter.

Appends one event per block/ask to .raven/.cache/signal-queue.json. Aggregated
and shipped to Hub by stream-signal.py at session Stop — same pipeline used by
mcp-guard, pr-signal, loc-tracker.

Fails silent by design: a queue-write error must NEVER change the block/ask
decision. If we can't record the audit, the hook still exits cleanly.

Secrets: target and reason often capture the raw Bash command that was blocked,
which can contain bearer tokens, API keys, and hardcoded credentials. Every
event is passed through _scrub_secrets() before being written so the ledger
never stores those verbatim (patterns mirror agent/scripts/secret-scan.py).

Concurrency: two hooks firing near-simultaneously (or two Claude sessions on
the same project) can race the read-modify-write of the queue file. We hold an
OS-level exclusive lock on the queue for the whole append cycle — POSIX uses
fcntl.flock, Windows uses msvcrt.locking. Lock failures fall through to the
outer try/except: fail silent, never flip a block into an allow.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MAX_TARGET_LEN = 200
_MAX_REASON_LEN = 300
_MAX_PATTERN_LEN = 200

# Secret patterns — kept in sync with agent/scripts/secret-scan.py so the same
# tokens flagged pre-commit are also scrubbed from the audit ledger. Each match
# is replaced with a fixed marker plus type so the ledger still records that a
# secret-shaped string was involved, without exposing the token itself.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"),                                                    "AWS_ACCESS_KEY"),
    (re.compile(r"(?i)aws.{0,20}secret.{0,20}[\"'][A-Za-z0-9+/]{40}[\"']"),              "AWS_SECRET"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"),                                                 "OPENAI_KEY"),
    (re.compile(r"(?i)(api[_-]?key|api[_-]?secret)\s*=\s*[\"'][A-Za-z0-9+/._-]{16,}[\"']?"), "API_KEY"),
    (re.compile(r"(?i)password\s*=\s*[\"'][^\"']{8,}[\"']"),                             "PASSWORD"),
    (re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA) PRIVATE KEY-----"),                   "PRIVATE_KEY"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}"),                                "BEARER_TOKEN"),
    (re.compile(r"(?i)(secret_key|private_key)\s*=\s*[\"'][^\"']{8,}[\"']"),             "SECRET_KEY"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"),                                              "GOOGLE_KEY"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"),                                                 "GITHUB_PAT"),
    (re.compile(r"xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}"),                            "SLACK_BOT"),
]


def _scrub_secrets(value: str) -> str:
    """Replace secret-shaped substrings with [REDACTED:TYPE] markers.

    Returns the input unchanged if no patterns match. Applied to target and
    reason before the truncation + write, so the audit ledger never stores
    raw bearer tokens or API keys captured from a blocked command line.
    """
    if not value:
        return value
    scrubbed = value
    for pattern, label in _SECRET_PATTERNS:
        scrubbed = pattern.sub(f"[REDACTED:{label}]", scrubbed)
    return scrubbed


# ── Cross-platform advisory lock on the queue file ────────────────────────────
# fcntl.flock is POSIX-only; Windows Python ships msvcrt.locking. Both calls
# block until the lock is available. Kept in a try/import so a missing module
# on either platform can't crash the hook — the outer try/except in emit does.
try:
    import fcntl  # POSIX

    def _lock_exclusive(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
except ImportError:
    import msvcrt  # Windows

    def _lock_exclusive(fd: int) -> None:
        # LK_LOCK blocks with internal retry (~10s) — sufficient for the very
        # short critical section held here (one JSON parse + append + write).
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock(fd: int) -> None:
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


def _queue_path() -> Path:
    """Resolve the signal queue path relative to CLAUDE_PROJECT_DIR (or CWD)."""
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    return root / ".raven" / ".cache" / "signal-queue.json"


def _truncate(value: Any, limit: int) -> str:
    if value is None:
        return ""
    s = str(value)
    return s if len(s) <= limit else s[:limit]


def emit_damage_event(
    *,
    tool: str,
    decision: str,
    reason: str,
    target: str,
    pattern: str = "",
    session_id: str = "",
) -> None:
    """Append one damage-control audit event to the signal queue.

    tool      — "Bash" | "Edit" | "Write"
    decision  — "blocked" | "asked"
    reason    — human-readable reason (already prefixed with "Blocked:" etc.)
    target    — the command (Bash) or file path (Edit/Write) — truncated
    pattern   — optional pattern that matched (helps analytics)
    session_id — Claude Code session id if present in the hook stdin
    """
    try:
        # Scrub secrets BEFORE truncation. Truncation on a redacted string still
        # yields a safe result; truncation before scrubbing would cut a secret
        # mid-match and leave the tail readable in the ledger.
        safe_reason = _truncate(_scrub_secrets(str(reason) if reason else ""), _MAX_REASON_LEN)
        safe_target = _truncate(_scrub_secrets(str(target) if target else ""), _MAX_TARGET_LEN)
        event = {
            "event_type": "damage_control",
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": str(tool)[:16],
            "decision": str(decision)[:16],
            "reason": safe_reason,
            "pattern": _truncate(pattern, _MAX_PATTERN_LEN),
            "target": safe_target,
            "session_id": _truncate(session_id, 64),
        }
        path = _queue_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Open the queue file for read+write (creating if missing). We hold an
        # OS-level exclusive lock across the read → append → write so two hooks
        # racing on the same project directory can't clobber each other's
        # appends. "a+" gives us a file descriptor with the file created if it
        # didn't exist; we seek(0) to read from the top.
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock_exclusive(fd)
            try:
                raw = os.read(fd, 16 * 1024 * 1024)  # 16 MiB is orders of magnitude beyond any real queue
                queue: list = []
                if raw:
                    try:
                        parsed = json.loads(raw.decode("utf-8"))
                        if isinstance(parsed, list):
                            queue = parsed
                    except Exception:
                        # Corrupt / partial write from a previous run — reset
                        # rather than lose the current event.
                        queue = []
                queue.append(event)
                payload = json.dumps(queue, indent=2).encode("utf-8")
                # Truncate + rewrite from position 0. Under the exclusive lock
                # no other writer is inside this section, so a full rewrite is
                # safe (the file grows monotonically for the session).
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, payload)
                os.ftruncate(fd, len(payload))
            finally:
                _unlock(fd)
        finally:
            os.close(fd)
    except Exception:
        # Fail silent — never let audit-emit turn allow into block.
        return
