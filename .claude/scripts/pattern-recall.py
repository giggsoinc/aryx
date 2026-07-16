"""pattern-recall.py — lightweight cross-session recall (T6.2, first version).

Scans your saved session notes and surfaces recurring patterns: projects and
topics you keep returning to ("you've touched auth in 6 sessions"). This is a
HONEST minimal version of cross-session learning — it counts what's in your
notes; it does not analyze your codebase or claim predictive insight.

Sources (read-only): ~/RavenVault/sessions/*.md (obsidian-log) and
.raven/memory/sessions/*.md (claude-mem). Modes: --recall (default) · --json.
Local-only, no telemetry.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

STOP = {"the", "and", "for", "with", "session", "raven", "andie", "fix", "the",
        "code", "this", "that", "from", "into", "your", "you", "are", "was",
        "entry", "note", "notes", "work", "task", "tasks", "summary", "what",
        "done", "open", "status", "date", "topic", "tags", "mode"}


def out(text: str = "") -> None:
    """Write a line to stdout (tool output contract, not logging)."""
    sys.stdout.write(text + "\n")


def note_files() -> list:
    """Return all session-note paths from both known sources."""
    files = []
    vault = Path.home() / "RavenVault" / "sessions"
    if vault.exists():
        files += list(vault.glob("*.md"))
    mem = Path(".raven/memory/sessions")
    if mem.exists():
        files += list(mem.glob("*.md"))
    return files


def scan(files: list) -> dict:
    """Tally recurring projects (from filename) and topic words (from notes)."""
    projects, topics = Counter(), Counter()
    for f in files:
        # filename pattern: YYYY-MM-DD-<project-or-topic>.md
        m = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", f.name)
        if m:
            projects[m.group(1)] += 1
        try:
            text = f.read_text(errors="ignore")[:4000].lower()
        except Exception:
            continue
        # topic words from frontmatter "tags:"/"topic:" lines, else headers
        for line in text.splitlines():
            if line.startswith(("tags:", "topic:", "# ", "## ")):
                for w in re.findall(r"[a-z][a-z0-9_-]{3,}", line):
                    if w not in STOP:
                        topics[w] += 1
    return {"projects": projects, "topics": topics, "total": len(files)}


def main() -> int:
    """Render recurring cross-session patterns."""
    as_json = "--json" in sys.argv
    files = note_files()
    data = scan(files)
    top_projects = data["projects"].most_common(5)
    top_topics = [(w, n) for w, n in data["topics"].most_common(12) if n > 1][:8]

    if as_json:
        out(json.dumps({
            "sessions_scanned": data["total"],
            "recurring_projects": top_projects,
            "recurring_topics": top_topics,
        }))
        return 0

    out("🪶 CROSS-SESSION RECALL")
    out("─" * 44)
    if not data["total"]:
        out("  No session notes yet — patterns appear after a few sessions.")
        return 0
    out(f"  Scanned {data['total']} saved session note(s).")
    if top_projects:
        out("\n  Projects you return to:")
        for name, n in top_projects:
            out(f"    • {name} — {n} session(s)")
    if top_topics:
        out("\n  Topics that keep coming up:")
        for word, n in top_topics:
            out(f"    • {word} — {n}×")
    out("\n  (Counts from your notes — a memory aid, not a prediction.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
