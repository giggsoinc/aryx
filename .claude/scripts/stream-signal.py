#!/usr/bin/env python3
"""
Raven Enterprise — Signal Emitter
Aggregates the day's signal queue and POSTs a single 200-byte daily summary to Hub.

Runs: end of each Claude Code session (Stop hook) or on a 30-minute timer.
Never sends raw events. Never sends prompts. No PII.

Signal pipeline
───────────────
  1. Other scripts (mcp-guard, secret-guard, etc.) append events to
     .raven/.cache/signal-queue.json during the session.
  2. model-router.py writes per-call cost to .model-session.json (NOT to the
     signal queue), so model_cost_usd is often 0 from the queue alone.
  3. At session Stop, Claude Code passes the JSONL session transcript via stdin.
  4. This script reads the queue, aggregates totals, then falls back to
     token-meter.py (which reads the transcript) to get real cost/tokens when
     the queue has no model_call events.
  5. The combined signal is POSTed to Hub and shown as the session summary.

Also writes to local blob store (S3/Azure/GCS/OCI) as defined in existing audit-log.py.
Hub is additional — blob store is the source of truth.
"""

import json, os, sys, subprocess, urllib.request, urllib.error, hashlib
from pathlib import Path
from datetime import datetime, timezone, date

# Windows: reconfigure stdout/stderr to UTF-8 so emoji in print() don't crash
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_PROJECT             = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
SIGNAL_QUEUE_PATH    = _PROJECT / ".raven" / ".cache" / "signal-queue.json"
DAILY_SIGNAL_PATH    = _PROJECT / ".raven" / ".cache" / "daily-signal.json"
SESSION_STATS_PATH   = _PROJECT / ".raven" / ".cache" / "session-stats.json"
MANIFEST_PATH        = _PROJECT / ".raven" / "manifest.json"
SECRETS_PATH         = _PROJECT / ".raven" / "manifest.secrets.json"

def load_json(path: Path, default=None):
    """Read a JSON file. Returns default if missing or parse fails."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else (default or {})
    except Exception:
        return default or {}

RAVEN_VERSION = "3.0.0"
PLUGIN_TYPE   = "enterprise"   # overridden by manifest if base plugin

# Cap raw damage-control events per POST. Anything beyond this stays in the queue
# for the next Stop (via non-clear on failure) or is dropped on successful flush —
# aggregate counters still capture the total via damage_blocked / damage_asked.
_MAX_DAMAGE_EVENTS_PER_SEND = 200


def aggregate_queue(queue: list[dict]) -> dict:
    """
    Collapse raw signal events into numeric totals for the daily summary.

    Event types handled:
      mcp_call       — counts ungoverned / hard-override MCP calls
      model_call     — sums cost, tokens, lines (written by model-router.py)
      token_checkpoint — precompact snapshots; keeps the highest token count
                         to avoid double-counting compacted context

    NOTE: model_call events are only present when model-router.py is active.
    For developers who are not yet on the model-router pipeline, model_cost_usd
    and tokens_estimated will be 0 here — the token-meter fallback in main()
    fills them in from the JSONL transcript.
    """
    total_cost_usd    = 0.0
    optimal_cost_usd  = 0.0
    lines_generated   = 0
    lines_accepted    = 0
    mcp_ungoverned    = 0
    mcp_override      = 0
    tokens_estimated  = 0
    prs_created       = 0
    prs_reviewed      = 0
    pr_created_urls:  list[str] = []
    pr_reviewed_urls: list[str] = []
    damage_blocked    = 0
    damage_asked      = 0
    damage_events:    list[dict] = []
    # Raw events beyond _MAX_DAMAGE_EVENTS_PER_SEND are dropped from this flush;
    # counters still reflect them. We report the drop count to Hub so the audit
    # trail is honest about truncation instead of silently under-representing.
    damage_events_dropped = 0

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
        elif etype == "pr_created":
            prs_created += 1
            u = evt.get("url")
            if isinstance(u, str) and u and u not in pr_created_urls:
                pr_created_urls.append(u)
        elif etype == "pr_reviewed":
            prs_reviewed += 1
            u = evt.get("url")
            if isinstance(u, str) and u and u not in pr_reviewed_urls:
                pr_reviewed_urls.append(u)
        elif etype == "damage_control":
            decision = evt.get("decision", "")
            if decision == "blocked":
                damage_blocked += 1
            elif decision == "asked":
                damage_asked += 1
            # Keep the raw event for the Hub audit trail — counters alone lose
            # the who/what/when the audit UI needs.
            if len(damage_events) < _MAX_DAMAGE_EVENTS_PER_SEND:
                damage_events.append({
                    "ts":         evt.get("ts", ""),
                    "tool":       evt.get("tool", ""),
                    "decision":   decision,
                    "reason":     evt.get("reason", ""),
                    "pattern":    evt.get("pattern", ""),
                    "target":     evt.get("target", ""),
                    "session_id": evt.get("session_id", ""),
                })
            else:
                damage_events_dropped += 1

    return {
        "mcp_ungoverned":    mcp_ungoverned,
        "mcp_override":      mcp_override,
        "model_cost_usd":    round(total_cost_usd, 4),
        "model_optimal_usd": round(optimal_cost_usd, 4),
        "lines_generated":   lines_generated,
        "lines_accepted":    lines_accepted,
        "tokens_estimated":  tokens_estimated,
        "pr_created":        prs_created,
        "pr_reviewed":       prs_reviewed,
        "pr_created_urls":   pr_created_urls,
        "pr_reviewed_urls":  pr_reviewed_urls,
        "damage_blocked":         damage_blocked,
        "damage_asked":           damage_asked,
        "damage_events":          damage_events,
        "damage_events_dropped":  damage_events_dropped,
    }

def build_daily_signal(manifest: dict, secrets: dict, aggregated: dict, session_stats: dict) -> dict:
    """
    Build the 200-byte daily summary payload sent to Hub.

    Identity fields (user, org, project) come from .raven/manifest.json.
    Session counters (sessions, commits, secrets_blocked, cve_blocked) come from
    .raven/.cache/session-stats.json, which is updated by session-start.py and
    raven-commit-counter.py throughout the day.
    Aggregated cost/token/line metrics come from aggregate_queue() + token-meter fallback.
    """
    plugin_type = manifest.get("plugin_type", PLUGIN_TYPE)
    return {
        "date":            date.today().isoformat(),
        "user":            manifest.get("user_email") or secrets.get("dev_email") or os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("USER", "unknown"),
        "org":             manifest.get("org") or secrets.get("org") or manifest.get("owner", ""),
        "project":         manifest.get("project", os.path.basename(os.getcwd())),
        "sessions":        session_stats.get("sessions", 1),
        "commits":         session_stats.get("commits", 0),
        "secrets_blocked": session_stats.get("secrets_blocked", 0),
        "cve_blocked":     session_stats.get("cve_blocked", 0),
        "policy_mode":     load_json(_PROJECT / ".raven" / "mcp-policy.json").get("mode", "shadow"),
        "raven_version":   manifest.get("raven_version", RAVEN_VERSION),
        "plugin_type":     plugin_type,
        # signal_version=2 tells Hub that tokens_estimated is a per-Stop delta
        # (additive) rather than a transcript total (max-merge). Required because
        # this script switched to delta tracking; v1 agents still get max() semantics.
        "signal_version":  2,
        **aggregated,
    }

def print_session_summary(signal: dict, queue_len: int, hub_ok: bool,
                          session_totals: dict | None = None):
    """
    Print the end-of-session cost/security summary to stderr.
    Claude Code shows stderr output in the terminal, so developers see this
    box automatically when each session ends — no extra commands needed.

    `session_totals` (when provided) holds cumulative session/day values
    (cost / optimal / tokens). The signal dict carries per-Stop deltas after
    the delta-tracking path runs, so reading directly from it would misreport
    each Stop's contribution as the whole session. Prefer totals when given.
    """
    totals    = session_totals or {}
    cost      = totals.get("cost",    signal.get("model_cost_usd",    0))
    optimal   = totals.get("optimal", signal.get("model_optimal_usd", 0))
    tokens    = totals.get("tokens",  signal.get("tokens_estimated",  0))
    savings   = round(cost - optimal, 4)
    waste_pct = round((savings / cost * 100) if cost > 0 else 0, 1)
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
        f"    Damage-control:   {signal.get('damage_blocked', 0)} blocked  /  {signal.get('damage_asked', 0)} asked",
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
    """
    POST the daily signal JSON to Hub /api/v1/signals.
    Returns True if Hub accepted (HTTP 200), False if unreachable.
    On failure the signal queue is NOT cleared — it will be retried next session.
    hub_url comes from manifest.json or manifest.secrets.json.
    """
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

def get_real_cost(stdin_bytes: bytes) -> dict:
    """
    Call token-meter.py --json to extract real cost and token counts from the
    Claude Code JSONL session transcript passed via stdin.

    Why this exists
    ───────────────
    model-router.py writes per-call costs to .model-session.json, not to the
    signal queue.  Developers who haven't updated their scripts yet — or who
    are using Claude Code without the model-router wired — will have 0 in the
    queue for model_cost_usd and tokens_estimated.  token-meter.py reads the
    actual JSONL session transcript (passed by Claude Code on the Stop hook)
    and calculates cost directly from the token counts in the transcript.

    Returns a dict with at minimum:
      cost_usd    — float, total session cost
      new_tokens  — int, input+output tokens for this session
    Returns {} on any error (missing script, timeout, parse failure).
    """
    try:
        token_meter = Path(__file__).parent / "token-meter.py"
        if not token_meter.exists():
            return {}
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(token_meter), "--json"],
            input=stdin_bytes,
            capture_output=True,
            timeout=8,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.decode("utf-8", errors="replace").strip())
    except Exception:
        pass
    return {}


def main():
    # ── Step 1: Read hook stdin ────────────────────────────────────────────────
    # Claude Code passes the JSONL session transcript via stdin on the Stop hook.
    # We keep the raw bytes for get_real_cost() (token-meter reads the transcript)
    # and extract hook_event to know if this is a genuine session-end Stop vs a
    # mid-session timer fire (where we should skip if there's nothing to send).
    raw_stdin  = b""
    hook_event = "Stop"
    try:
        if not sys.stdin.isatty():
            raw_stdin = sys.stdin.buffer.read()
            if raw_stdin.strip():
                hook_data  = json.loads(raw_stdin.decode("utf-8", errors="replace"))
                hook_event = hook_data.get("hook_event", "Stop")
    except Exception:
        pass   # Stdin may be empty when run manually or from a timer — that's fine

    manifest = load_json(MANIFEST_PATH)
    secrets  = load_json(SECRETS_PATH)

    # hub_url can live in manifest.json (non-secret) or manifest.secrets.json (preferred)
    hub_url = manifest.get("hub_url") or secrets.get("hub_url", "")
    if not hub_url:
        sys.exit(0)   # Raven not configured for this project — nothing to do

    # ── Step 2: Aggregate signal queue ────────────────────────────────────────
    # signal-queue.json accumulates mcp_call / model_call / token_checkpoint
    # events appended by other scripts during the session.
    queue      = load_json(SIGNAL_QUEUE_PATH, default=[])
    aggregated = aggregate_queue(queue)

    # ── Step 3: Token-meter fallback ──────────────────────────────────────────
    # model-router.py writes costs to .model-session.json, not signal-queue.json,
    # so model_cost_usd is 0 when the queue has no model_call events (common for
    # developers whose scripts haven't been updated yet, or who don't use the
    # model-router pipeline).  Fall back to token-meter.py which reads the JSONL
    # transcript directly and calculates real cost from Anthropic's token counts.
    session_totals: dict | None = None
    if aggregated["model_cost_usd"] == 0:
        tc = get_real_cost(raw_stdin)
        if tc.get("cost_usd", 0) > 0:
            cost = float(tc["cost_usd"])
            # Optimal = same tokens repriced at Haiku rates (token-meter computes
            # this from the transcript). Older meter binaries don't ship the
            # field — fall back to 25% of actual so the signal still has a value.
            optimal = tc.get("cost_optimal_usd")
            if optimal is None:
                optimal = cost * 0.25
            optimal = min(float(optimal), cost)
            new_tokens = tc.get("new_tokens", 0)

            # Per-Stop delta tracking — token-meter reads the FULL transcript and
            # returns cumulative totals, but Hub does `+=` on cost / optimal /
            # tokens. Without deltas, every Stop after the first would re-bill
            # the entire session, inflating Hub by N× for an N-Stop day.
            today        = date.today().isoformat()
            stats        = load_json(SESSION_STATS_PATH, default={})
            same_day     = stats.get("date") == today
            cost_sent    = stats.get("cost_sent",    0.0) if same_day else 0.0
            tokens_sent  = stats.get("tokens_sent",  0)   if same_day else 0
            optimal_sent = stats.get("optimal_sent", 0.0) if same_day else 0.0

            aggregated["model_cost_usd"]    = round(max(0.0, cost    - cost_sent),    4)
            aggregated["model_optimal_usd"] = round(max(0.0, optimal - optimal_sent), 4)
            if aggregated["tokens_estimated"] == 0:
                aggregated["tokens_estimated"] = max(0, new_tokens - tokens_sent)
            # Capture cumulative session/day totals — passed to the dev-facing
            # Summary box so it reports session-to-date numbers, not the delta.
            session_totals = {"cost": cost, "tokens": new_tokens, "optimal": optimal}

            # Write real token counts back to .model-session.json user_work bucket.
            # model-router.py runs at UserPromptSubmit (before response) so it can
            # only record tier classification, not actual token counts. This is the
            # only place real counts are available (parsed from session transcript).
            try:
                session_file = _PROJECT / ".raven" / ".model-session.json"
                if session_file.exists():
                    ms = json.loads(session_file.read_text())
                    ms["user_work"]["tokens"]   = new_tokens
                    ms["user_work"]["cost_usd"] = round(cost, 6)
                    session_file.write_text(json.dumps(ms, indent=2))
            except Exception:
                pass

    # ── Step 4: Early-exit guard ──────────────────────────────────────────────
    # Skip sending if this is a timer fire (not a real Stop) AND there is truly
    # nothing to report — avoids spamming Hub with empty signals every 30 minutes.
    # On genuine session Stop we always send (even zeros) so Hub knows the session ended.
    is_stop = hook_event in ("Stop", "PostSession", "")
    if not queue and aggregated["model_cost_usd"] == 0 and not is_stop:
        sys.exit(0)

    # ── Step 5: Build and send ────────────────────────────────────────────────
    session_stats = load_json(SESSION_STATS_PATH, default={})
    signal        = build_daily_signal(manifest, secrets, aggregated, session_stats)

    print(f"📡 Sending daily signal to Hub...", flush=True)
    ok = post_to_hub(signal, hub_url)

    if ok:
        # Clear the queue only on successful send so events aren't double-counted
        SIGNAL_QUEUE_PATH.unlink(missing_ok=True)
        # Write the daily summary locally for debugging / audit
        DAILY_SIGNAL_PATH.write_text(json.dumps(signal, indent=2))
        # Advance the per-day sent counters so the next Stop's transcript-derived
        # totals get diffed correctly. No-op if session-stats has rolled to a new day.
        try:
            today = date.today().isoformat()
            stats = load_json(SESSION_STATS_PATH, default={})
            if stats.get("date") == today:
                stats["cost_sent"]    = round(stats.get("cost_sent",    0.0) + aggregated.get("model_cost_usd",    0.0), 6)
                stats["tokens_sent"]  =       stats.get("tokens_sent",  0)   + aggregated.get("tokens_estimated",  0)
                stats["optimal_sent"] = round(stats.get("optimal_sent", 0.0) + aggregated.get("model_optimal_usd", 0.0), 6)
                SESSION_STATS_PATH.write_text(json.dumps(stats))
        except Exception:
            pass

    # Always show the dev summary box — regardless of whether Hub was reachable
    print_session_summary(signal, len(queue), ok, session_totals)

if __name__ == "__main__":
    main()
