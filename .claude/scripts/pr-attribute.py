#!/usr/bin/env python3
"""
Raven — PR Description Auto-Populator (Sprint A4.1).

Composes an attribution summary table from the staged docs/contribute/*.md
files of the most recent commit, splices it into the PR body between the
<!-- raven-contribute-begin --> / <!-- raven-contribute-end --> markers, and
calls `gh pr edit` to apply.

Idempotent. Safe to re-run. Fails silent if gh CLI is absent.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

MARKER_BEGIN = "<!-- raven-contribute-begin -->"
MARKER_END = "<!-- raven-contribute-end -->"

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))


def _gh(*args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["gh", *args], capture_output=True, timeout=15)
        return r.returncode, r.stdout.decode()
    except FileNotFoundError:
        return 127, ""
    except Exception:
        return 1, ""


def changed_files_in_head() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return [ln.strip() for ln in out.decode().splitlines() if ln.strip()]
    except Exception:
        return []


def _doc_summary(doc_path: Path) -> str:
    if not doc_path.exists():
        return ""
    try:
        text = doc_path.read_text(errors="ignore")
    except Exception:
        return ""
    head_lines = []
    for line in text.splitlines():
        if line.startswith("Total lines:") or line.startswith("Lines AI"):
            head_lines.append(line)
        if line.startswith("Owner"):
            head_lines.append(line)
    return " · ".join(head_lines)


def build_table(changed: list[str]) -> str:
    rows = ["| File | Attribution summary |", "| ---- | ------------------- |"]
    for rel in changed:
        if rel.startswith("docs/contribute/"):
            continue
        doc = ROOT / "docs/contribute" / (rel + ".md")
        summary = _doc_summary(doc) or "(no attribution data)"
        rows.append(f"| `{rel}` | {summary} |")
    return "\n".join(rows)


def splice(body: str, table: str) -> str:
    block = f"{MARKER_BEGIN}\n## Raven attribution\n\n{table}\n{MARKER_END}"
    if MARKER_BEGIN in body and MARKER_END in body:
        pattern = re.compile(
            re.escape(MARKER_BEGIN) + r"[\s\S]*?" + re.escape(MARKER_END))
        return pattern.sub(block, body)
    return body.rstrip() + "\n\n" + block + "\n"


def main() -> int:
    changed = [c for c in changed_files_in_head()
                if not c.startswith("docs/contribute/")]
    if not changed:
        return 0
    table = build_table(changed)
    rc, body = _gh("pr", "view", "--json", "body", "-q", ".body")
    if rc == 127:
        sys.stderr.write("  gh CLI not installed — skipping PR update\n")
        return 0
    if rc != 0:
        # No PR yet, or other failure — non-blocking
        return 0
    new_body = splice(body or "", table)
    proc = subprocess.run(
        ["gh", "pr", "edit", "--body-file", "-"],
        input=new_body.encode(), capture_output=True, timeout=15,
    )
    return 0 if proc.returncode == 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
