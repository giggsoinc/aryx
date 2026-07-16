#!/usr/bin/env python3
"""Live current-session token + cost meter (makes the F2 claim true).

Reads the CURRENT session transcript JSONL and sums real API usage per turn
(input, output, cache-write, cache-read) with per-model cache-aware pricing, so
the number is live and accurate on demand — unlike the session-start "Last
session" line, which shows the PRIOR session.

Modes: --current (banner) · --statusline (compact, cost-led) · --json
Source: ~/.claude/projects/<slug>/<session_id>.jsonl. Local-only, no telemetry.
"""
import argparse
import json
import pathlib
import sys

# Per-model price per MTok USD: (input, output, cache_write, cache_read).
# Public list prices; override at .raven/pricing.json.
DEFAULT_PRICING = {
    "haiku": (0.80, 4.00, 1.00, 0.08),
    "sonnet": (3.00, 15.00, 3.75, 0.30),
    "opus": (15.00, 75.00, 18.75, 1.50),
}


def out(text: str) -> None:
    """Write one line to stdout (the tool's output contract; not logging)."""
    sys.stdout.write(text + "\n")


def load_pricing() -> dict:
    """Return the pricing table, merging .raven/pricing.json if present."""
    override = pathlib.Path(".raven/pricing.json")
    if override.exists():
        try:
            return {**DEFAULT_PRICING, **json.loads(override.read_text())}
        except Exception:
            pass
    return DEFAULT_PRICING


def rate_for(model: str, pricing: dict) -> tuple:
    """Match a model id to a price tuple by family substring; default sonnet."""
    m = (model or "").lower()
    for family, rates in pricing.items():
        if family in m:
            return rates
    return pricing["sonnet"]


def find_transcript() -> str:
    """Locate the current session transcript.

    Priority: hook stdin (session_id / transcript_path) -> most-recent JSONL in
    the project's slug dir -> most-recent JSONL anywhere under ~/.claude/projects.
    """
    session_id, transcript_path = "", ""
    if not sys.stdin.isatty():
        try:
            hook = json.load(sys.stdin)
            session_id = hook.get("session_id", "")
            transcript_path = hook.get("transcript_path", "")
        except Exception:
            pass
    if transcript_path and pathlib.Path(transcript_path).exists():
        return transcript_path
    projects = pathlib.Path.home() / ".claude" / "projects"
    if session_id:
        hits = list(projects.glob(f"**/{session_id}.jsonl"))
        if hits:
            return str(hits[0])
    # Claude project slugs replace BOTH "/" and "_" with "-".
    slug = str(pathlib.Path.cwd()).replace("/", "-").replace("_", "-")
    slug_dir = projects / slug
    candidates = list(slug_dir.glob("*.jsonl")) if slug_dir.exists() else []
    if not candidates:
        candidates = list(projects.glob("**/*.jsonl"))
    return str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else ""


def tally(path: str, pricing: dict) -> dict:
    """Sum tokens and cache-aware cost across assistant turns in the transcript.

    Also re-prices the same tokens at the cheapest tier (Haiku) to give an
    `optimal` cost — the floor of what this workload could have cost if every
    turn ran on the cheapest viable model. A Haiku-only session yields
    cost == optimal (waste = 0); a Sonnet/Opus session yields optimal < cost.
    """
    haiku_rates = pricing.get("haiku", (0.80, 4.00, 1.00, 0.08))
    t = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
         "cost": 0.0, "optimal": 0.0, "turns": 0, "models": set()}
    for line in open(path):
        try:
            msg = json.loads(line).get("message", {})
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        u = msg.get("usage")
        if not u or not u.get("output_tokens"):
            continue
        i, o = u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0
        cw = u.get("cache_creation_input_tokens", 0) or 0
        cr = u.get("cache_read_input_tokens", 0) or 0
        r_in, r_out, r_cw, r_cr = rate_for(msg.get("model", ""), pricing)
        h_in, h_out, h_cw, h_cr = haiku_rates
        t["input"] += i
        t["output"] += o
        t["cache_write"] += cw
        t["cache_read"] += cr
        # Anthropic's usage fields are three SEPARATE buckets — input_tokens is
        # already exclusive of cache reads/writes. Bill each at its own rate.
        t["cost"]    += (i * r_in + o * r_out + cw * r_cw + cr * r_cr) / 1_000_000
        t["optimal"] += (i * h_in + o * h_out + cw * h_cw + cr * h_cr) / 1_000_000
        t["turns"] += 1
        if msg.get("model"):
            t["models"].add(msg["model"])
    return t


def main() -> int:
    """Parse args, locate the current transcript, and emit the meter."""
    ap = argparse.ArgumentParser(description="Live session token + cost meter")
    ap.add_argument("--statusline", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--current", action="store_true")
    args = ap.parse_args()

    path = find_transcript()
    if not path:
        out("🪶 tok: n/a" if args.statusline
            else json.dumps({"error": "no transcript found"}) if args.json
            else "🪶 token-meter: no current-session transcript found yet.")
        return 0

    t = tally(path, load_pricing())
    new = t["input"] + t["output"] + t["cache_write"]  # freshly billed this session
    if args.statusline:
        out(f"🪶 ${t['cost']:.2f} · {new/1000:.0f}K new")
    elif args.json:
        out(json.dumps({
            "cost_usd": round(t["cost"], 4),
            "cost_optimal_usd": round(min(t["optimal"], t["cost"]), 4),
            "new_tokens": new,
            "cache_read_tokens": t["cache_read"], "input": t["input"],
            "output": t["output"], "cache_write": t["cache_write"],
            "turns": t["turns"], "models": sorted(t["models"])}))
    else:
        out("🪶 LIVE SESSION METER (current session, from transcript)")
        out(f"   Cost so far    : ~${t['cost']:.4f}   ({t['turns']} model turns)")
        out(f"   New tokens     : {new:,}  (in {t['input']:,} · out {t['output']:,} · cache-write {t['cache_write']:,})")
        out(f"   Context reused : {t['cache_read']:,} cache-read (discounted ~90%)")
        out(f"   Models         : {', '.join(sorted(t['models'])) or 'n/a'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
