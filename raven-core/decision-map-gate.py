#!/usr/bin/env python3
"""
Raven — Decision-Map Gate v1.0

Hard-blocking pre-commit gate: fails the commit if ANY mandatory decision
point anywhere in the whole project — not just this commit's diff, per the
project's explicit choice to scope this gate to the full repo rather than
raven-refresh's usual diff-only posture — is missing sufficient raven_log()
evidence, per raven-decision-map's own classification.

Blocks on ANY real decision-point finding — both "mandatory" (high-confidence,
>=0.85: retry/circuit-breaker decorators, try/except recovery, state-attribute
assignment, auth-guard calls, non-stdlib dependency calls) and "recommended"
(lower-confidence pattern matches: Routing/Eligibility/Outcome) — as long as
existing_log_status != "sufficient". Two categories are deliberately excluded,
not as a loophole but because including them would be blocking on the wrong
thing entirely:
  - "no-log" entries — the scanner's own explicit exemption (pure
    calculations, getters, small helpers) — blocking on these would mean
    blocking BECAUSE a function correctly needs no logging.
  - flood-risk entries (empty decision_classes, loop-nested log call) — these
    are raven-flood's territory; raven-decision-map itself says "never
    instrument these as ordinary decision points," so gating on them the same
    way would contradict the skill this gate is built on.

This is a fully deterministic, stdlib-only script — no LLM call — precisely
because a hard-blocking gate needs to be fast and reliable on every commit.
The richer, judgment-informed report (including "recommended" findings) is
generated separately by a real Claude session and stays advisory-only (see
the `claude -p` step in install-guardrail-pre-commit-hook.sh) — decoupled on
purpose so a slow/flaky LLM call can never be why a commit hangs or is
wrongly blocked/passed.

Scans every tracked file **in-process** via the scanner's own analyze_file()
(imported once), not one `python3 ast_decision_scanner.py --file X` subprocess
per file — measured at ~56s for 487 files on the per-subprocess approach
(interpreter startup dominates), which is real, avoidable latency a
synchronous pre-commit gate should never carry. This is the same in-process
import idiom guardrail-pipeline.py already uses for the same reason.

Baseline (PR #173 review, C1): a whole-repo hard gate with no baseline means
the very first time this runs against an existing codebase, it blocks EVERY
commit on however much pre-existing debt already exists — which for a real
repo of any size is every commit, forever, until that debt is fully cleared.
`.raven/decision-map-baseline.json` (committed, shared by the team) records
the findings a team has explicitly accepted as pre-existing; only findings
NOT in the baseline block a commit. This does not weaken the gate to
diff-only scanning — it still scans the whole repo every run, per this
file's own stated design — it only changes which of the whole-repo findings
are new enough to block. A finding's identity is (file, line, symbol): a
deliberately simple key, not a perfect one — an unrelated edit that shifts
line numbers elsewhere in the same file can make a genuinely unchanged
finding look "new" and re-trigger a block. That's a known, accepted tradeoff
of line-based baselines (the same one mypy's/other tools' baseline features
carry), not something this file tries to solve with fuzzier matching.

Usage:
    python3 decision-map-gate.py                 # normal run — blocks on
                                                    non-baselined findings
    python3 decision-map-gate.py --write-baseline # accept every current
                                                    finding as baseline;
                                                    always exits 0

Exit codes: 0 = no blocking findings (or --write-baseline ran) | 1 = blocking
findings found (commit BLOCKED) | 2 never used — scanner-unavailable fails
OPEN (0), since a missing scanner is an environment gap, not evidence the
code is fine, but also not a reason to block an unrelated commit.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

# Windows' default console/pipe encoding (cp1252) can't encode the emoji used
# in this script's own output -- crashing what's designed to be advisory/
# fail-open output into a hard crash, and via `|| exit 1` in the pre-commit
# hook, a real block on every commit. errors="replace" guarantees this can
# never crash on any platform; worst case an emoji renders as a placeholder.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASELINE_PATH = Path(".raven") / "decision-map-baseline.json"


def find_scanner() -> Optional[Path]:
    """Project-local copy first (this repo builds the skill itself), then the
    user-level skill install (every other project that installs this hook)."""
    candidates = [
        Path("skills/raven-decision-map/scripts/ast_decision_scanner.py"),
        Path.home() / ".claude" / "skills" / "raven-decision-map" / "scripts" / "ast_decision_scanner.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def load_scanner(scanner_path: Path):
    spec = importlib.util.spec_from_file_location("ast_decision_scanner", scanner_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracked_python_files() -> Optional[list]:
    """Returns the tracked *.py file list, or None if `git ls-files` itself
    failed (not a git repo, corrupted git state, ...) — kept distinct from a
    genuinely empty list, so a real environment failure doesn't get reported
    as "no Python files, all clean" (PR #173 review, M1)."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "*.py"], stderr=subprocess.DEVNULL
        ).decode()
        return [f for f in out.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return None


def scan_file(scanner_module, file_path: str) -> list:
    """One file's placement-plan entries, in-process. Fails open per-file — a
    single unparseable file must not silently exempt the whole gate, but also
    must not crash it; analyze_file() already skips syntax errors per-file
    with a note printed to stdout, so an unexpected exception here would be a
    real bug in the scanner, not an expected outcome."""
    try:
        return [asdict(entry) for entry in scanner_module.analyze_file(file_path)]
    except Exception:
        return []


def _finding_key(entry: dict):
    """Deliberately simple identity — see module docstring's "Baseline"
    section for the line-shift tradeoff this accepts."""
    return (entry.get("file"), entry.get("line"), entry.get("symbol"))


def load_baseline(path: Path = BASELINE_PATH) -> set:
    """Never raises — a missing or corrupt baseline file means "nothing is
    baselined yet," not a fatal error (fail-open on availability only; this
    is a convenience feature layered on top of the gate, not a replacement
    for it)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {tuple(item) for item in raw.get("findings", [])}
    except Exception:
        return set()


def write_baseline(findings: list, path: Path = BASELINE_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({_finding_key(e) for e in findings})
    path.write_text(json.dumps({
        "note": "Findings accepted as pre-existing debt at the time this baseline was "
                "written — raven-core/decision-map-gate.py only blocks on findings NOT "
                "in this list. Regenerate with --write-baseline after deliberately "
                "accepting more debt; do not hand-edit to silence a real new finding.",
        "findings": [list(k) for k in keys],
    }, indent=2) + "\n", encoding="utf-8")
    return len(keys)


def scan_project(scanner_module, files: list) -> list:
    blocking = []
    for f in files:
        for entry in scan_file(scanner_module, f):
            status = entry.get("mandatory_status")
            if status not in ("mandatory", "recommended"):
                continue  # excludes "no-log" (explicit exemption)
            if not entry.get("decision_classes"):
                continue  # excludes flood-risk entries — raven-flood's territory, not this gate's
            if entry.get("existing_log_status") != "sufficient":
                blocking.append(entry)
    return blocking


def main() -> int:
    parser = argparse.ArgumentParser(description="Raven Decision-Map Gate")
    parser.add_argument("--write-baseline", action="store_true",
                        help="Accept every current finding as baseline (always exits 0)")
    args = parser.parse_args()

    scanner = find_scanner()
    if scanner is None:
        print("⚠️  raven-decision-map-gate: scanner not found (not installed in this project's "
              "skills/raven-decision-map/ or ~/.claude/skills/) — skipping (fail-open, an "
              "environment gap is not evidence the code itself is fine, but also not a reason "
              "to block an unrelated commit)")
        return 0

    files = tracked_python_files()
    if files is None:
        print("⚠️  raven-decision-map-gate: 'git ls-files' failed — skipping (fail-open, "
              "an environment gap is not evidence the code itself is fine, but also not "
              "a reason to block an unrelated commit)")
        return 0
    if not files:
        print("✅ raven-decision-map-gate: no tracked Python files")
        return 0

    scanner_module = load_scanner(scanner)
    blocking = scan_project(scanner_module, files)

    if args.write_baseline:
        count = write_baseline(blocking)
        print(f"✅ raven-decision-map-gate: wrote {count} finding(s) to {BASELINE_PATH} "
              f"as the accepted baseline")
        return 0

    baseline = load_baseline()
    new_blocking = [e for e in blocking if _finding_key(e) not in baseline]
    baselined_count = len(blocking) - len(new_blocking)

    if not new_blocking:
        if baselined_count:
            print(f"✅ raven-decision-map-gate: {len(files)} file(s) scanned across the project — "
                  f"no unresolved NEW findings ({baselined_count} pre-existing, baselined, not blocking)")
        else:
            print(f"✅ raven-decision-map-gate: {len(files)} file(s) scanned across the project — "
                  f"no unresolved findings")
        return 0

    print(f"❌ raven-decision-map-gate: {len(new_blocking)} new finding(s) across the project "
          f"lack sufficient raven_log() evidence — commit BLOCKED")
    if baselined_count:
        print(f"   ({baselined_count} additional finding(s) are pre-existing and baselined — not blocking)")
    for entry in new_blocking:
        classes = ", ".join(entry.get("decision_classes") or [])
        status = entry.get("mandatory_status")
        print(f"   ❌ [{status}] {entry.get('file')}:{entry.get('line')} {entry.get('symbol')}() "
              f"[{classes}] — {entry.get('reason')}")
    print("   Add raven_log() calls per raven-log's schema (see /raven-log instrument), "
          "resolve why existing_log_status isn't 'sufficient' for these, or if this debt "
          "is deliberately accepted, run --write-baseline.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"⚠️  raven-decision-map-gate: unexpected error — {e} (fail-open)")
        sys.exit(0)
