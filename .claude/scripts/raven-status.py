#!/usr/bin/env python3
"""raven-status.py — transparent feedback banner (T4.4).

Makes Raven's normally-silent protection VISIBLE and positive, so a new developer
sees "you're covered" instead of only meeting Raven when a commit is blocked.
Shows: guards available, skills available, session notes, and the live token cost.

Run on demand:  python3 .claude/scripts/raven-status.py
Plain English. No jargon. Local-only, no telemetry.
"""
import subprocess
import sys
from pathlib import Path


def out(text: str) -> None:
    """Write one line to stdout (the banner's output contract, not logging)."""
    sys.stdout.write(text + "\n")


def count_dir(path: str, pattern: str) -> int:
    """Count files/dirs matching a glob under path (0 if path is absent)."""
    p = Path(path)
    return len(list(p.glob(pattern))) if p.exists() else 0


def live_tokens() -> str:
    """Ask token-meter for a compact live cost line; '' if unavailable."""
    meter = Path(__file__).parent / "token-meter.py"
    if not meter.exists():
        return ""
    try:
        r = subprocess.run(
            ["python3", str(meter), "--statusline"],
            capture_output=True, text=True, timeout=8,
            stdin=subprocess.DEVNULL)  # avoid blocking on inherited stdin
        return r.stdout.strip()
    except Exception:
        return ""


def session_notes() -> int:
    """Count saved session notes for any project (carry-forward journal)."""
    vault = Path.home() / "RavenVault" / "sessions"
    return len(list(vault.glob("*.md"))) if vault.exists() else 0


def main() -> int:
    """Render the plain-English status banner."""
    guards = count_dir("agents", "*.md")
    skills = count_dir("skills", "*/") or count_dir(
        "plugin/.claude-plugin/skills", "*/")
    has_manifest = Path(".raven/manifest.json").exists()
    notes = session_notes()
    tokens = live_tokens()

    out("🪶 RAVEN — you're covered")
    out("─" * 48)
    out(f"  🛡  {guards} guards watching — they only speak up if something's")
    out("      risky (a secret, a known-vulnerable library, a destructive")
    out("      git/db action). Silence means you're clear.")
    out(f"  🧰  {skills} skills on tap — load only when your task needs them.")
    if has_manifest:
        out("  📋  Project manifest found — Raven knows your stack.")
    else:
        out("  📋  No manifest yet — say 'andie init' when you want one.")
    if notes:
        out(f"  📓  {notes} session note(s) saved (carry-forward, in ~/RavenVault).")
    if tokens:
        out(f"  {tokens}   (this session's real cost so far)")
    out("─" * 48)
    out("  New here? See docs/START-HERE.md for the 5-minute mental model.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
