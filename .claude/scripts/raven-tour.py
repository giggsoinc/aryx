#!/usr/bin/env python3
"""raven-tour.py — interactive 5-minute onboarding walkthrough (EPIC 4 / T4.1).

A real paced terminal tour: it explains the mental model one step at a time,
waits for you between steps, runs the live status/meter so you SEE the system,
and points at the next thing to try. Plain English, no jargon walls.

Run:  python3 .claude/scripts/raven-tour.py   (Enter to advance, q to quit)
Local-only. Read-only (it only runs read-only status scripts).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def out(text: str = "") -> None:
    """Write a line to stdout (tour output contract, not logging)."""
    sys.stdout.write(text + "\n")


def pause(step: int, total: int) -> bool:
    """Wait for the user; return False if they want to quit."""
    try:
        ans = input(f"\n  [{step}/{total}] Enter to continue, q to quit > ")
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.strip().lower() not in ("q", "quit", "exit")


def run_script(name: str, *args: str) -> str:
    """Run a sibling read-only script and return its output ('' on failure)."""
    p = HERE / name
    if not p.exists():
        return ""
    try:
        r = subprocess.run(["python3", str(p), *args], capture_output=True,
                           text=True, timeout=10, stdin=subprocess.DEVNULL)
        return r.stdout.strip()
    except Exception:
        return ""


def main() -> int:
    """Run the interactive tour, step by step."""
    steps = [
        ("Welcome", [
            "🪶 Raven, in one picture:",
            "   you type a request → Raven quietly points big/risky work at a",
            "   helper and checks your commits → Claude does the work → you ship.",
            "   Most of the time you won't notice it. It speaks up only when it",
            "   helps (planning) or protects (a risky commit)."]),
        ("Your status right now", None),       # runs raven-status
        ("The two helpers", [
            "🧭 Andie     — when you face a design choice, it shows the problem",
            "              from 3 angles before you commit (catches blind spots).",
            "🔧 Andie-jr  — when you report a bug, it runs a structured debug:",
            "              problem → root cause → fix → why.",
            "   Missed when you wanted it? Type /andie or /andie-jr to force it."]),
        ("What this session has cost", None),  # runs token-meter
        ("Watch a guard protect you (safe demo)", [
            "Try this in a scratch repo: put a fake API key in a file and commit.",
            "Raven's secret check stops the commit and tells you how to fix it —",
            "that block is protection, not a scolding. Silence = you're clear."]),
        ("Where to go next", [
            "📖 docs/START-HERE.md   — this, in writing, plus a jargon decoder",
            "📖 docs/ROUTING.md      — exactly when Andie / Andie-jr fire",
            "🪶 raven-status.py      — your live protection + cost, any time",
            "You're set. Welcome to Raven."]),
    ]
    total = len(steps)
    out("\n" + "═" * 52)
    out("  RAVEN — 5-MINUTE INTERACTIVE TOUR")
    out("═" * 52)
    for i, (title, lines) in enumerate(steps, 1):
        out(f"\n▶ {title}")
        out("─" * 52)
        if lines is None and "status" in title.lower():
            out(run_script("raven-status.py") or "  (status unavailable)")
        elif lines is None:
            out("  " + (run_script("token-meter.py", "--current")
                        or "(token meter unavailable)"))
        else:
            for ln in lines:
                out("  " + ln)
        if i < total and not pause(i, total):
            out("\n  👋 Tour ended early — run again any time.")
            return 0
    out("\n" + "═" * 52)
    return 0


if __name__ == "__main__":
    sys.exit(main())
