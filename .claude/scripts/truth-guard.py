#!/usr/bin/env python3
"""
truth-guard.py — T1.5 enforcement (Raven truth-policy).

Blocks commits that re-introduce known-false / unverified marketing claims into
docs. This is the enforced version of the realstory_andie.md.env rule:
"No claim ships unless it appears as TRUE."

A rule that isn't enforced is the silent-guard problem. This makes it a hard gate.

Scope: staged *.md files only. Exits non-zero (blocks commit) on any hit.
Override: `git commit --no-verify` (logged by intent, not by us).
"""
import subprocess
import sys
import re

# (regex pattern, why it's blocked, suggested honest replacement)
BANNED = [
    (r"\bfull powers\b",
     "inflation — 'Full Powers' adds no engineered capability",
     "say 'Andie v6.3' and list what it does/doesn't do"),
    # NOTE: no "memory" phrase-guard here on purpose. `.raven/memory/sessions/` is a
    # LEGITIMATE path (the claude-mem agent uses it), and any phrase like "live
    # memory" appears as often in honest NEGATIONS ("there is no live memory") as in
    # false claims — a regex can't tell them apart and would block true statements.
    # Memory-claim accuracy is enforced by review + .raven/andie-v6.3-audit-correction.md,
    # not by this list. Only ban phrases that are inherently affirmative marketing.
    (r"all tests passed",
     "invalid verification if 'tests' were grep-for-headers",
     "state what was actually run and what it proves"),
    (r"\b60 skills?\b",
     "stale count",
     "verify with: ls -d skills/*/ | wc -l (then state total + specialist split)"),
    (r"always[ -]on (guard|hook)",
     "MISLEADING (F4) — guards fire on matching conditions, not always",
     "'guards fire when conditions match'"),
    (r"(reduces|saves|cuts) .{0,12}current[- ]session token",
     "FALSE (F1/F2) — no current-session token reduction exists",
     "'session continuity / carry-forward for the next session'"),
    (r"expert system|breakthrough reasoning",
     "MISLEADING (M3) — it's prompt templates + routing",
     "'prompt-structured modes' / 'multi-angle review'"),
    (r"continuous(ly)?\s+OODA|OODA\s+(runs?\s+)?continuous(ly)?|adaptive\s+OODA",
     "MISLEADING (M4) — OODA is a linear per-round checkpoint, not an always-on loop",
     "'OODA runs as a checkpoint after each round'"),
]

def staged_md_files():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True,
    ).stdout
    return [f for f in out.splitlines() if f.endswith(".md")]

def staged_content(path):
    return subprocess.run(
        ["git", "show", f":{path}"], capture_output=True, text=True
    ).stdout

def is_git_commit_hook():
    """PreToolUse mode: read hook JSON from stdin; return True only if the tool
    call is a `git commit`. Any read error or non-commit command → False."""
    import json as _json
    try:
        payload = _json.load(sys.stdin)
    except Exception:
        return False
    cmd = (payload.get("tool_input", {}) or {}).get("command", "")
    return bool(re.search(r"\bgit\s+commit\b", cmd))


def main():
    hook_mode = "--hook" in sys.argv
    # In hook mode we only act on `git commit`; everything else passes silently.
    if hook_mode and not is_git_commit_hook():
        return 0

    hits = []
    for path in staged_md_files():
        # Docs that DOCUMENT claims (the truth-policy source, audit records, status
        # ledgers) are allowed to quote the very phrases we ban elsewhere.
        low = path.lower()
        if (path.endswith(".md.env") or "truth-guard" in path
                or any(k in low for k in ("audit", "status", "consolidat", "ledger", "handover"))):
            continue
        content = staged_content(path)
        for pattern, why, fix in BANNED:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                line = content[:m.start()].count("\n") + 1
                hits.append((path, line, m.group(0), why, fix))

    if not hits:
        if not hook_mode:
            print("truth-guard: clean — no banned claims in staged docs")
        return 0

    out = sys.stderr if hook_mode else sys.stdout
    print("=" * 70, file=out)
    print(f"truth-guard BLOCKED commit — {len(hits)} unverified claim(s)", file=out)
    print("=" * 70, file=out)
    for path, line, found, why, fix in hits:
        print(f"\n  {path}:{line}", file=out)
        print(f"    found:   '{found}'", file=out)
        print(f"    why:     {why}", file=out)
        print(f"    fix:     {fix}", file=out)
    print("\n" + "-" * 70, file=out)
    print("Fix the wording, or override with --no-verify if you've verified it's true.", file=out)
    # Claude Code PreToolUse convention: exit 2 = block tool & feed stderr back.
    # Plain git pre-commit convention: exit 1 = block commit.
    return 2 if hook_mode else 1

if __name__ == "__main__":
    sys.exit(main())
