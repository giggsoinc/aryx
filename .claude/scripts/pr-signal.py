#!/usr/bin/env python3
"""
Raven Enterprise — PR Signal Emitter
Detects PR creation and review from Bash PostToolUse context,
then appends an event to the signal queue for stream-signal.py to pick up.

Each emitted event carries the GitHub PR URL when it can be recovered:
  - pr_created  → URL is parsed from `gh pr create` stdout (gh prints it on success)
  - pr_reviewed → URL is built from the PR number in the command + origin remote

If the URL can't be recovered, the event is still emitted (count-only) so totals
stay correct — the URL just stays out of the Hub payload for that event.

Two modes:
  Hook mode (stdin):  called from PostToolUse Bash hook — parses tool context
  Direct mode (args): python3 pr-signal.py --event pr_reviewed [--url https://...]

╔════════════════════════════════════════════════════════════════════════╗
║  WHY THIS FILE LIVES IN THREE PLACES                                    ║
║  ──────────────────────────────────                                      ║
║  Identical copies of this script exist at three deployment roots:        ║
║    • raven-core/pr-signal.py            ← canonical source (edit here)   ║
║    • agent/scripts/pr-signal.py         ← bundled into the agent install ║
║    • .claude/scripts/pr-signal.py       ← active hook for this project   ║
║                                                                          ║
║  Claude Code's hook runtime resolves scripts by absolute path; it does   ║
║  not honor Python import paths for hook entry points, so a shared module ║
║  cannot be sourced at runtime without an install-time wrapper at every   ║
║  deployment root. Until that wrapper exists, the three copies stay byte- ║
║  identical and any change MUST be applied to all three. Drift between    ║
║  them is a real bug — `diff -q` the three files in CI before merging.    ║
║                                                                          ║
║  Tracked deduplication work: planned but out of scope for this PR.       ║
╚════════════════════════════════════════════════════════════════════════╝
"""

import json, os, re, subprocess, sys, tempfile
from pathlib import Path

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None  # Windows: no flock, best-effort only

SIGNAL_QUEUE_PATH = Path(".raven/.cache/signal-queue.json")

# Matches any github.com PR URL — used to scrape `gh pr create` stdout.
PR_URL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+")

def load_queue() -> list:
    try:
        if SIGNAL_QUEUE_PATH.exists():
            data = json.loads(SIGNAL_QUEUE_PATH.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def emit(event_type: str, url: str | None = None):
    """Append a PR event to the signal queue using a file lock + atomic write."""
    SIGNAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = SIGNAL_QUEUE_PATH.parent / "signal-queue.lock"
    try:
        lock_fd = open(lock_path, "w")
    except Exception:
        return
    try:
        if _fcntl:
            _fcntl.flock(lock_fd, _fcntl.LOCK_EX)
        queue = load_queue()
        event: dict = {"event_type": event_type}
        if url:
            event["url"] = url
        queue.append(event)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=SIGNAL_QUEUE_PATH.parent, suffix=".tmp")
        try:
            os.write(tmp_fd, json.dumps(queue, indent=2).encode())
            os.close(tmp_fd)
            os.replace(tmp_path, str(SIGNAL_QUEUE_PATH))
        except Exception:
            try:
                os.close(tmp_fd)
            except Exception:
                pass
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    finally:
        if _fcntl:
            _fcntl.flock(lock_fd, _fcntl.LOCK_UN)
        lock_fd.close()


def _validated_pr_url(url: str | None) -> str | None:
    """Return `url` only if it fully matches PR_URL_RE; else None.

    Used to gate values coming from untrusted sources (CLI `--url` flag,
    eventually arbitrary tool_response payloads). Uses fullmatch so a
    benign-looking prefix can't carry trailing junk like a query string
    with a javascript: URL or shell metacharacters.
    """
    if not isinstance(url, str) or not url:
        return None
    return url if PR_URL_RE.fullmatch(url) else None


def _stringify_response_field(value: str | list | None) -> str:
    """Flatten a tool_response field (str / list of str-or-dict) into one string."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text") or item.get("content")
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    return ""


def _origin_owner_repo() -> str | None:
    """Return 'owner/repo' parsed from `git remote get-url origin`, or None."""
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode != 0:
            return None
        url = (r.stdout or "").strip()
    except Exception:
        return None
    # Matches https://github.com/OWNER/REPO[.git]  or git@github.com:OWNER/REPO[.git]
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def extract_pr_url(tool_response: dict, command: str) -> str | None:
    """Recover the GitHub PR URL from a successful gh pr create/review invocation."""
    # 1) gh pr create prints the PR URL on stdout. Claude Code's tool_response
    #    may carry the output under stdout / output / content, so check all three.
    haystack = "\n".join(
        _stringify_response_field(tool_response.get(k))
        for k in ("stdout", "output", "content")
    )
    m = PR_URL_RE.search(haystack)
    if m:
        return m.group(0)

    # 2) gh pr review <N>: stdout doesn't include the URL — construct it from
    #    origin + the PR number parsed out of the command line.
    cmd_lower = command.lower()
    if "gh pr review" in cmd_lower:
        # First non-flag token after `review` is the PR number (or a branch/URL).
        m = re.search(r"gh\s+pr\s+review\s+(?:-{1,2}\S+\s+)*(\d+)", command, re.IGNORECASE)
        if m:
            pr_num = m.group(1)
            owner_repo = _origin_owner_repo()
            if owner_repo:
                return f"https://github.com/{owner_repo}/pull/{pr_num}"
    return None


def main():
    # Direct invocation: pr-signal.py --event <type> [--url <url>]
    if "--event" in sys.argv:
        idx = sys.argv.index("--event")
        if idx + 1 < len(sys.argv):
            event_type = sys.argv[idx + 1]
            url = None
            if "--url" in sys.argv:
                u_idx = sys.argv.index("--url")
                if u_idx + 1 < len(sys.argv):
                    # Validate against PR_URL_RE — direct-mode is reachable from
                    # the shell, so we can't trust the caller. Mismatches are
                    # silently dropped: the count event still fires, just URL-less.
                    url = _validated_pr_url(sys.argv[u_idx + 1])
            if event_type in ("pr_created", "pr_reviewed"):
                emit(event_type, url)
        sys.exit(0)

    # Hook invocation: PostToolUse pipes JSON context via stdin
    ctx = {}
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                ctx = json.loads(raw)
    except Exception:
        sys.exit(0)

    tool_response = ctx.get("tool_response", {}) or {}

    # Claude Code sets isError=True on Bash failures; "error" key is also present on failure.
    # Mirrors the pattern used by audit-log.py: tool_response.get("error") is None → success.
    if tool_response.get("isError") or tool_response.get("error") is not None:
        sys.exit(0)

    command = (ctx.get("tool_input", {}).get("command") or "")
    cmd_lower = command.lower()

    # Guard against --help and --dry-run invocations that exit 0 without creating a PR.
    # For reviews, the flag-action variants (--approve/--comment/--request-changes) and the
    # bare interactive form (`gh pr review <N>`) both count — cancelled/failed runs already
    # exit non-zero and are filtered by the isError check above.
    if "gh pr create" in cmd_lower and "--help" not in cmd_lower and "--dry-run" not in cmd_lower:
        emit("pr_created", extract_pr_url(tool_response, command))
    elif "gh pr review" in cmd_lower and "--help" not in cmd_lower:
        emit("pr_reviewed", extract_pr_url(tool_response, command))

if __name__ == "__main__":
    main()
