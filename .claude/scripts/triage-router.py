#!/usr/bin/env python3
"""
Raven — Triage Router (v4.1+)

Deterministic routing: brownfield default = Andie-jr, greenfield default = Andie.

Rules (NO regex classification):
  1. Brownfield (git exists + commits > 1) → Andie-jr (unless pure data question)
  2. Greenfield (no .git OR ≤1 commit) → Andie (planning first)
  3. Data-only question (explicit keywords, no code change) → direct answer
  4. Force overrides: /andie, /andie-jr always work (T3.1)

Repo state is the signal. If we have code history, we debug with Andie-jr.
If we don't, we plan with Andie first.

Local-only. No telemetry. ~60 LOC.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from router_common import force_intent, semantic_fallback, log_overhead
except Exception:  # fail-soft: routing still works without the shared helper
    def force_intent(_p): return None
    def semantic_fallback(_p, _k): return False
    def log_overhead(_s, _t): return None


def is_brownfield() -> bool:
    """Return True if repo has git history (existing codebase)."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=".", capture_output=True, timeout=1, text=True
        )
        if result.returncode == 0:
            count = int(result.stdout.strip())
            return count > 1  # more than one commit = brownfield
    except Exception:
        pass
    return False


def is_data_question(prompt: str) -> bool:
    """Return True if this is a pure data/question (no code change expected).

    Keywords: read, explain, show, count, list, how does, what is, find, grep, etc.
    Must NOT mention: build, create, write, fix, change, refactor, implement, deploy.
    """
    if not prompt or len(prompt) < 10:
        return False

    data_keywords = {
        "read", "explain", "show", "count", "list", "what", "where", "when",
        "how does", "find", "grep", "search", "query", "describe", "summarize",
        "tell me", "give me", "what is", "why", "how do i", "can you", "help me understand"
    }
    change_keywords = {
        "build", "create", "write", "fix", "change", "refactor", "implement",
        "deploy", "add", "remove", "delete", "update", "modify", "rewrite"
    }

    prompt_lower = prompt.lower()
    has_data_keyword = any(kw in prompt_lower for kw in data_keywords)
    has_change_keyword = any(kw in prompt_lower for kw in change_keywords)

    return has_data_keyword and not has_change_keyword


def classify(prompt: str) -> Optional[str]:
    """Return 'andie-jr' for brownfield, 'andie' for greenfield, None for data-only."""
    if is_data_question(prompt):
        return None  # direct answer, no skill invoked

    if is_brownfield():
        return "andie-jr"  # existing code = debug/fix mode
    else:
        return "andie"  # new project = planning mode


def main() -> None:
    """Route based on repo state (brownfield → Andie-jr, greenfield → Andie).

    Order: explicit force (T3.1) → repo state classify → opt-in semantic fallback (T3.2).
    """
    prompt = os.environ.get("PROMPT", "")
    if not prompt:
        try:
            raw = sys.stdin.read()
            try:
                data = json.loads(raw)
                prompt = data.get("prompt", raw)
            except Exception:
                prompt = raw
        except Exception:
            return

    # T3.1: explicit force always wins
    forced = force_intent(prompt)
    if forced == "andie":
        return  # architect-router owns the andie force path
    if forced == "andie-jr":
        _emit_andie_jr(prompt)
        return

    # Deterministic routing by repo state
    routed_to = classify(prompt)
    if routed_to == "andie-jr":
        _emit_andie_jr(prompt)
    elif routed_to == "andie":
        _emit_andie(prompt)
    # else: routed_to is None → data question, no skill needed


def _emit_andie_jr(prompt: str) -> None:
    """Emit [ANDIE-JR REQUIRED] injection."""
    emission = (
        "[ANDIE-JR REQUIRED] Brownfield repo detected. MANDATORY: invoke "
        "`andie-jr` skill BEFORE any diagnosis, file read, bash command, or "
        "response. Andie-jr structures the debug flow: problem -> root cause -> "
        "fix -> why -> audit note.\n"
    )
    sys.stdout.write(emission)
    log_overhead("triage-router", emission)


def _emit_andie(prompt: str) -> None:
    """Emit [ANDIE REQUIRED] injection."""
    emission = (
        "[ANDIE REQUIRED] Greenfield project detected. MANDATORY: invoke "
        "`andie` skill BEFORE any coding. Andie structures planning: problem -> "
        "angles -> decisions -> plan. Then /andie-jr for implementation.\n"
    )
    sys.stdout.write(emission)
    log_overhead("triage-router", emission)


if __name__ == "__main__":
    main()
