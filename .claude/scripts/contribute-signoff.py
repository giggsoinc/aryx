#!/usr/bin/env python3
"""
Raven — Auto-Signoff (Sprint A4.4) post-commit hook.

Reads the files changed in HEAD, enqueues one signoff per file with
signer = committer for the local-to-Hub sync queue. Idempotent via the
Hub-side UNIQUE (file_id, commit_sha).

Also triggers PR description update via pr-attribute.py.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def _load_queue():
    spec = importlib.util.spec_from_file_location(
        "_q", Path(__file__).resolve().parent / "contribute-queue.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return ""


def changed_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return [ln.strip() for ln in out.decode().splitlines() if ln.strip()
                and not ln.startswith("docs/contribute/")]
    except Exception:
        return []


def signer() -> str:
    try:
        return subprocess.check_output(
            ["git", "log", "-1", "--pretty=%ae"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return os.environ.get("GIT_AUTHOR_EMAIL", "unknown")


def enqueue_signoffs(project_id: str) -> int:
    q = _load_queue()
    sha = head_sha()
    if not sha:
        return 0
    files = changed_files()
    if not files:
        return 0
    s = signer()
    for f in files:
        q.enqueue("signoffs", project_id,
                  {"file_path": f, "commit_sha": sha, "signer_email": s})
    return len(files)


def trigger_pr_update() -> None:
    script = Path(__file__).resolve().parent / "pr-attribute.py"
    if not script.exists():
        return
    try:
        subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def project_id() -> str:
    pid = os.environ.get("RAVEN_PROJECT_ID", "")
    if pid:
        return pid
    # Fallback: hash of repo path → deterministic per checkout (dev mode).
    import hashlib
    return hashlib.sha1(str(Path.cwd()).encode()).hexdigest()[:32]


def main() -> int:
    try:
        n = enqueue_signoffs(project_id())
        if n:
            trigger_pr_update()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
