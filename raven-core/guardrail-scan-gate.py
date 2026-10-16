#!/usr/bin/env python3
"""
Raven — Guardrail Scan Gate v1.0 (task T31, implementing T01's decision)

The concrete "third outcome" auto-log-guardrail-plugin-cross-cutting-decisions.md's T01
called for and log-coverage-check.py's plain exit-code convention doesn't provide:

    log-coverage-check.py:  0 = pass | 1 = fail | 2 = fail-open (scanner error, silent,
                             never blocks — this is a *counting* gate with downstream
                             backstops, so a scanner bug silently not-enforcing one run
                             is an acceptable cost)

    guardrail-scan-gate.py: 0 = ran clean | 0 = COULD NOT RUN, but the commit is still
                             not silently treated as scanned — a flag record is written
                             to .raven/audit/guardrail-scan-flags/ instead. "Fail-closed"
                             for this gate never meant "block the commit" (see T01) — it
                             means "never let a scan that didn't actually happen look
                             identical, from the outside, to one that did."

This script never blocks a commit by itself — it always exits 0 (installed as a
non-fatal step in the pre-commit hook by
install-guardrail-pre-commit-hook.sh). Blocking on guardrail *findings* (an actual gap
detected) is Section D's human-approval-gate territory (Phase 2), a separate concern
from this gate's job, which is purely "did the scan run at all."

Usage (installed by install-guardrail-pre-commit-hook.sh into .git/hooks/pre-commit):
    python3 guardrail-scan-gate.py --staged
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows' default console/pipe encoding (cp1252) can't encode the emoji used
# in this script's own output -- crashing what's designed to be advisory/
# fail-open output into a hard crash. errors="replace" guarantees this can
# never crash on any platform; worst case an emoji renders as a placeholder.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
_SCANNER = _HERE.parent / "skills" / "raven-decision-map" / "scripts" / "ast_decision_scanner.py"
_FLAG_DIR = Path(".raven") / "audit" / "guardrail-scan-flags"


def _staged_files() -> list:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            stderr=subprocess.DEVNULL,
        ).decode()
        return [f for f in out.splitlines() if f.strip()]
    except Exception:
        return []


def run_scan(staged: bool = True, scanner_path: Path = None, run=None):
    """Invoke ast_decision_scanner.py --staged as a subprocess (it already
    implements staged-file discovery itself — no need to duplicate it here).
    Returns (ok, entries_or_none, reason). `run` is injectable for tests."""
    scanner = scanner_path or _SCANNER
    if not scanner.exists():
        return False, None, "SCANNER_MISSING"

    runner = run or subprocess.run
    try:
        args = [sys.executable, str(scanner)] + (["--staged"] if staged else [])
        proc = runner(args, capture_output=True, text=True, timeout=60)
    except Exception:
        return False, None, "SCANNER_CRASHED"

    if proc.returncode not in (0, 1):
        # ast_decision_scanner.py's own fail-open convention treats non-0/1 as
        # "did not complete" — matches log-coverage-check.py's exit-2 posture.
        return False, None, "SCANNER_NONZERO_EXIT"

    try:
        entries = json.loads(proc.stdout) if proc.stdout.strip() else []
    except json.JSONDecodeError:
        return False, None, "SCANNER_OUTPUT_UNPARSEABLE"

    return True, entries, ""


def write_flag(reason: str, staged_files: list, flag_dir: Path = None) -> Path:
    """The evidence artifact T01 asked for: an explicit, audit-queryable
    record that the guardrail scan did not run for this commit — never a
    silent skip. Keyed by content so re-running an identical failed attempt
    doesn't pile up duplicate flags for the same staged set."""
    d = flag_dir or _FLAG_DIR
    d.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        (reason + "|" + "|".join(sorted(staged_files))).encode()).hexdigest()[:16]
    path = d / f"{digest}.json"
    path.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "staged_files": staged_files,
        "note": "guardrail-injection scan did not complete for this commit — "
                "commit proceeded, unguarded and explicitly flagged (T01)",
    }, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Raven Guardrail Scan Gate")
    parser.add_argument("--staged", action="store_true", default=True)
    args = parser.parse_args()

    staged_files = _staged_files()
    ok, entries, reason = run_scan(staged=args.staged)

    if ok:
        print(f"✅ [raven-guardrail] decision-map scan ran clean "
              f"({len(entries)} finding(s) over {len(staged_files)} staged file(s))",
              file=sys.stderr)
        sys.exit(0)

    flag_path = write_flag(reason, staged_files)
    print(f"⚠️  [raven-guardrail] decision-map scan unavailable this commit "
          f"({reason}) — flagged, not blocking. See {flag_path}", file=sys.stderr)
    sys.exit(0)  # never blocks — see module docstring


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠️  guardrail-scan-gate: unexpected error — {e} (fail-open, not blocking)",
              file=sys.stderr)
        sys.exit(0)
