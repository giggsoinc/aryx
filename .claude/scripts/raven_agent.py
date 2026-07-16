#!/usr/bin/env python3
"""
Raven Agent Routing — Model Tier Resolution + Token Tracking

NOT a direct Agent() wrapper (Agent is a Claude Code tool, not a Python class).
Instead, this script:
1. Reads the current tier from .raven/.model-session.json
2. Resolves the model for that tier from .model.env
3. Maps tier to Claude Code's model parameter (sonnet/opus/haiku)
4. Logs agent invocations for cost tracking

Skills read the output to set the `model` parameter on Agent() calls.

Usage (CLI — called by hooks or skills):
  python3 raven_agent.py --tier COMPLEX
  python3 raven_agent.py                    # reads from .model-session.json
  python3 raven_agent.py --log --skill andie --subagent plan --tier COMPLEX --duration 12.5

Usage (library):
  from raven_agent import resolve_model, log_agent_run
  model_param, model_full = resolve_model("COMPLEX")
  # model_param = "opus"  (for Agent(model="opus"))
  # model_full  = "anthropic/claude-opus-4-5"
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


# ── Tier → Claude Code model parameter ────────────────────────────────────────
# Agent() accepts: "sonnet", "opus", "haiku"
# This maps our tier to the right parameter value.

TIER_TO_CLAUDE_PARAM = {
    "SIMPLE":     "haiku",
    "MEDIUM":     "sonnet",
    "COMPLEX":    "opus",
    "LOCAL_ONLY": "haiku",  # local models handled separately
}


def resolve_model(tier: Optional[str] = None) -> Tuple[str, str]:
    """
    Resolve the model for a given tier.

    Args:
        tier: SIMPLE/MEDIUM/COMPLEX/LOCAL_ONLY. If None, reads from .model-session.json.

    Returns:
        (claude_param, full_model_string)
        claude_param: "haiku", "sonnet", or "opus" — for Agent(model=...)
        full_model_string: "anthropic/claude-opus-4-5" — for logging/display
    """
    if tier is None:
        tier = _get_session_tier()

    claude_param = TIER_TO_CLAUDE_PARAM.get(tier, "sonnet")
    full_model = _get_model_from_env(tier)

    # If .model.env says ollama, keep haiku param but note it's local
    if "ollama" in full_model or "lmstudio" in full_model:
        claude_param = "haiku"  # cheapest remote fallback if local unavailable

    return claude_param, full_model


def _get_session_tier() -> str:
    """Read current tier from .raven/.model-session.json."""
    session_file = Path.cwd() / ".raven" / ".model-session.json"
    if not session_file.exists():
        return "MEDIUM"
    try:
        data = json.loads(session_file.read_text())
        return data.get("tier", "MEDIUM")
    except Exception:
        return "MEDIUM"


def _get_model_from_env(tier: str) -> str:
    """Read model for tier from .model.env [routing] section."""
    for path in [Path.cwd() / ".model.env", Path.home() / ".model.env"]:
        if not path.exists():
            continue
        try:
            in_routing = False
            for line in path.read_text().splitlines():
                line = line.strip()
                if line == "[routing]":
                    in_routing = True
                    continue
                elif line.startswith("["):
                    in_routing = False
                    continue
                if in_routing and "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == tier:
                        return val.strip()
        except Exception:
            continue

    # Defaults
    defaults = {
        "SIMPLE": "anthropic/claude-haiku-4-5",
        "MEDIUM": "anthropic/claude-sonnet-4-5",
        "COMPLEX": "anthropic/claude-opus-4-5",
        "LOCAL_ONLY": "ollama/dolphin-mistral",
    }
    return defaults.get(tier, "anthropic/claude-sonnet-4-5")


def log_agent_run(
    skill: str,
    subagent_type: str,
    tier: str,
    model: str,
    duration_seconds: float = 0.0,
    tokens_estimated: int = 0,
) -> None:
    """
    Log an agent invocation to .raven/.cache/agent-runs.json.
    Called by skills after Agent() returns.
    """
    cache_dir = Path.cwd() / ".raven" / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_file = cache_dir / "agent-runs.json"

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "skill": skill,
        "subagent_type": subagent_type,
        "model_tier": tier,
        "model": model,
        "tokens_estimated": tokens_estimated,
        "duration_seconds": round(duration_seconds, 2),
    }

    try:
        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text())
            except (json.JSONDecodeError, Exception):
                entries = []
        if not isinstance(entries, list):
            entries = []

        entries.append(entry)
        entries = entries[-200:]  # keep last 200

        log_file.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        print(f"Warning: Failed to log agent run: {e}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resolve model for tier")
    parser.add_argument("--tier", help="SIMPLE/MEDIUM/COMPLEX/LOCAL_ONLY")
    parser.add_argument("--log", action="store_true", help="Log an agent run")
    parser.add_argument("--skill", default="unknown")
    parser.add_argument("--subagent", default="general")
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--tokens", type=int, default=0)
    args = parser.parse_args()

    if args.log:
        tier = args.tier or _get_session_tier()
        _, model = resolve_model(tier)
        log_agent_run(args.skill, args.subagent, tier, model, args.duration, args.tokens)
        print(json.dumps({"logged": True, "tier": tier, "model": model}))
        return

    tier = args.tier or _get_session_tier()
    claude_param, full_model = resolve_model(tier)

    print(json.dumps({
        "tier": tier,
        "claude_model_param": claude_param,
        "full_model": full_model,
        "agent_call_example": f'Agent(description="...", prompt="...", model="{claude_param}")',
    }, indent=2))


if __name__ == "__main__":
    main()
