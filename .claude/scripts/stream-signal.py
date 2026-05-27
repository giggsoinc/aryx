#!/usr/bin/env python3
"""
Raven Enterprise — Signal Emitter
Aggregates the day's signal queue and POSTs a single 200-byte daily summary to Hub.

Runs: end of each Claude Code session (PostSession hook) or on a 30-minute timer.
Never sends raw events. Never sends prompts. No PII.

Also writes to local blob store (S3/Azure/GCS/OCI) as defined in existing audit-log.py.
Hub is additional — blob store is the source of truth.
"""

import json, os, sys, urllib.request, urllib.error, hashlib
from pathlib import Path
from datetime import datetime, timezone, date

SIGNAL_QUEUE_PATH = Path(".raven/.cache/signal-queue.json")
DAILY_SIGNAL_PATH = Path(".raven/.cache/daily-signal.json")
MANIFEST_PATH     = Path(".raven/manifest.json")
SECRETS_PATH      = Path(".raven/manifest.secrets.json")

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text()) if path.exists() else (default or {})
    except Exception:
        return default or {}

RAVEN_VERSION = "3.0.0"
PLUGIN_TYPE   = "enterprise"   # overridden by manifest if base plugin

def aggregate_queue(queue: list[dict]) -> dict:
    """Collapse raw signal events into a single daily summary."""
    total_cost_usd    = 0.0
    optimal_cost_usd  = 0.0
    lines_generated   = 0
    lines_accepted    = 0
    mcp_ungoverned    = 0
    mcp_override      = 0
    tokens_estimated  = 0

    for evt in queue:
        etype = evt.get("event_type", "")
        if etype == "mcp_call":
            if not evt.get("registered", True):
                mcp_ungoverned += 1
            if evt.get("override") and evt["override"] not in ("shadow-auto", None):
                mcp_override += 1
        elif etype == "model_call":
            total_cost_usd   += evt.get("cost_usd", 0)
            optimal_cost_usd += evt.get("optimal_cost_usd", 0)
            lines_generated  += evt.get("lines_generated", 0)
            lines_accepted   += evt.get("lines_accepted", 0)
            tokens_estimated += evt.get("tokens_estimated", 0)
        elif etype == "token_checkpoint":
            # PreCompact fires give us token checkpoints
            tokens_estimated  = max(tokens_estimated, evt.get("tokens_estimated", 0))

    return {
        "mcp_ungoverned":    mcp_ungoverned,
        "mcp_override":      mcp_override,
        "model_cost_usd":    round(total_cost_usd, 4),
        "model_optimal_usd": round(optimal_cost_usd, 4),
        "lines_generated":   lines_generated,
        "lines_accepted":    lines_accepted,
        "tokens_estimated":  tokens_estimated,
    }

def build_daily_signal(manifest: dict, secrets: dict, aggregated: dict, session_stats: dict) -> dict:
    """Build the daily summary payload."""
    plugin_type = manifest.get("plugin_type", PLUGIN_TYPE)
    return {
        "date":            date.today().isoformat(),
        "user":            manifest.get("user_email") or os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("USER", "unknown"),
        "org":             manifest.get("org", ""),
        "project":         manifest.get("project", os.path.basename(os.getcwd())),
        "sessions":        session_stats.get("sessions", 1),
        "commits":         session_stats.get("commits", 0),
        "secrets_blocked": session_stats.get("secrets_blocked", 0),
        "cve_blocked":     session_stats.get("cve_blocked", 0),
        "policy_mode":     load_json(Path(".raven/mcp-policy.json")).get("mode", "shadow"),
        "raven_version":   manifest.get("raven_version", RAVEN_VERSION),
        "plugin_type":     plugin_type,
        **aggregated,
    }

def print_session_summary(signal: dict, queue_len: int, hub_ok: bool):
    """Print developer-facing end-of-session metrics to stderr (shown in Claude Code terminal)."""
    cost     = signal.get("model_cost_usd", 0)
    optimal  = signal.get("model_optimal_usd", 0)
    savings  = round(cost - optimal, 4)
    waste_pct = round((savings / cost * 100) if cost > 0 else 0, 1)
    tokens   = signal.get("tokens_estimated", 0)
    hub_line = "✅ Sent" if hub_ok else "⚠️  Queued (Hub offline)"

    lines = [
        "",
        "━" * 42,
        f"  Raven Session Summary — {signal['date']}",
        "━" * 42,
        f"  Project:    {signal['project']}",
        f"  Commits:    {signal.get('commits', 0)}",
        f"  Lines:      {signal.get('lines_generated', 0)} generated  /  {signal.get('lines_accepted', 0)} accepted",
        "",
        "  Security:",
        f"    Secrets blocked:  {signal.get('secrets_blocked', 0)}",
        f"    CVEs blocked:     {signal.get('cve_blocked', 0)}",
        f"    MCPs ungoverned:  {signal.get('mcp_ungoverned', 0)}  (logged)",
        "",
        "  Cost:",
        f"    Est. tokens:      ~{tokens:,}",
        f"    Est. cost:        ${cost:.4f}",
        f"    Optimal cost:     ${optimal:.4f}  (saving ${savings:.4f} / {waste_pct}%)",
        "",
        f"  Hub:  {hub_line}",
        "━" * 42,
        "",
    ]
    print("\n".join(lines), file=sys.stderr)

def post_to_hub(signal: dict, hub_url: str) -> bool:
    """POST daily signal to Raven Hub. Returns True on success."""
    url = hub_url.rstrip("/") + "/api/v1/signals"
    payload = json.dumps(signal).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "X-Raven-Agent": "enterprise-v1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False   # Hub unreachable — signal stays in queue for next attempt

def main():
    manifest = load_json(MANIFEST_PATH)
    secrets  = load_json(SECRETS_PATH)

    hub_url = manifest.get("hub_url") or secrets.get("hub_url", "")
    if not hub_url:
        # No Hub configured — local-only mode, nothing to send
        sys.exit(0)

    queue = load_json(SIGNAL_QUEUE_PATH, default=[])
    if not queue:
        sys.exit(0)

    aggregated    = aggregate_queue(queue)
    session_stats = load_json(Path(".raven/.cache/session-stats.json"), default={})
    signal        = build_daily_signal(manifest, secrets, aggregated, session_stats)

    print(f"📡 Sending daily signal to Hub...", flush=True)
    ok = post_to_hub(signal, hub_url)

    if ok:
        # Clear the queue only on successful send
        SIGNAL_QUEUE_PATH.unlink(missing_ok=True)
        DAILY_SIGNAL_PATH.write_text(json.dumps(signal, indent=2))

    # Always show dev summary regardless of Hub status
    print_session_summary(signal, len(queue), ok)

if __name__ == "__main__":
    main()
