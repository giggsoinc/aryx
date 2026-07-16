#!/usr/bin/env python3
"""
Raven — Local Metrics Rollup

Persists per-day developer activity into ~/RavenVault/.metrics/YYYY-MM.json so
dashboard.py has a rolling history of PRs, commits, lines, and guard activity
even when the Hub stream clears the local signal queue.

Runs as a Stop hook BEFORE stream-signal.py. Never blocks, never throws.

Data flow:
  Reads:
    .raven/.cache/signal-queue.json   — event stream (PRs, lines, MCP, models)
    .raven/.cache/session-stats.json  — today's running totals (commits, secrets, cve)
    .raven/manifest.json              — project / user identity
  Writes:
    ~/RavenVault/.metrics/YYYY-MM.json — month rollup, one row per (date, project, user)
  Mutates:
    .raven/.cache/signal-queue.json   — stamps processed events with _rolled_up=true
                                        so subsequent rollups don't double-count.

Schema of a session row inside the month file:
  {
    "date":             "2026-06-25",
    "started_at":       "2026-06-25T00:00:00+00:00",   # for dashboard.py window filter
    "project":          "raven-enterprise",
    "user":             "m.ahsan@giggso.com",
    "sessions":         2,
    "tokens":           12345,
    "cost_usd":         0.4521,
    "commits":          3,
    "pr_created":       1,
    "pr_reviewed":      2,
    "pr_created_urls":  ["https://github.com/..."],
    "pr_reviewed_urls": ["https://github.com/..."],
    "lines_generated":  234,
    "lines_accepted":   220,
    "secrets_blocked":  0,
    "cve_blocked":      0,
    "mcp_ungoverned":   0,
    "mcp_override":     0,
    "tier_counts":      {...},
    "tier_cost":        {...},
    "skills_used":      [...],
    "specialists_used": [...]
  }
"""

import importlib.util
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PROJECT      = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(Path.cwd()))).resolve()
CACHE_DIR     = _PROJECT / ".raven" / ".cache"
QUEUE_PATH    = CACHE_DIR / "signal-queue.json"
STATS_PATH    = CACHE_DIR / "session-stats.json"
SIGNAL_PATH   = CACHE_DIR / "last-signal.json"      # mirror of Hub payload (stream-signal writes)
MODEL_SESSION = _PROJECT / ".raven" / ".model-session.json"   # two-bucket attribution
MANIFEST_PATH = _PROJECT / ".raven" / "manifest.json"

VAULT_METRICS = Path.home() / "RavenVault" / ".metrics"


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _identity(manifest: dict) -> tuple[str, str]:
    project = manifest.get("project") or os.path.basename(os.getcwd())
    user = (
        manifest.get("user_email")
        or os.environ.get("GIT_AUTHOR_EMAIL")
        or os.environ.get("USER", "unknown")
    )
    return project, user


def _aggregate_unprocessed(queue: list[dict]) -> dict:
    """Tally events whose _rolled_up flag isn't set yet."""
    agg = {
        "pr_created": 0,
        "pr_reviewed": 0,
        "pr_created_urls": [],
        "pr_reviewed_urls": [],
        "lines_generated": 0,
        "lines_accepted": 0,
        "mcp_ungoverned": 0,
        "mcp_override": 0,
    }
    for evt in queue:
        if evt.get("_rolled_up"):
            continue
        etype = evt.get("event_type", "")
        if etype == "pr_created":
            agg["pr_created"] += 1
            url = evt.get("url")
            if isinstance(url, str) and url:
                agg["pr_created_urls"].append(url)
        elif etype == "pr_reviewed":
            agg["pr_reviewed"] += 1
            url = evt.get("url")
            if isinstance(url, str) and url:
                agg["pr_reviewed_urls"].append(url)
        elif etype == "model_call":
            agg["lines_generated"] += int(evt.get("lines_generated", 0) or 0)
            agg["lines_accepted"] += int(evt.get("lines_accepted", 0) or 0)
        elif etype == "mcp_call":
            if not evt.get("registered", True):
                agg["mcp_ungoverned"] += 1
            if evt.get("override") and evt["override"] not in ("shadow-auto", None):
                agg["mcp_override"] += 1
    return agg


def _import_stream_signal():
    """Load stream-signal.py as a module (the filename has a dash, so importlib).

    We reuse its compute_transcript_usage / pricing so cost numbers match the
    Hub's exactly — single source of truth.

    Safety: stream-signal.py guards its main() with `if __name__ == "__main__"`.
    exec_module triggers ONLY module-level code; main() is not run, so dashboard
    refreshes and rollups don't accidentally fire a Hub-send pipeline. If that
    guard is ever removed, this import must be replaced with a shared utility.
    """
    try:
        ss_path = Path(__file__).with_name("stream-signal.py")
        if not ss_path.exists():
            return None
        spec = importlib.util.spec_from_file_location("_raven_stream_signal", str(ss_path))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _encode_cwd(cwd: str) -> str:
    """Match Claude Code's transcript-dir encoding.

    Every path separator and underscore becomes '-'. Windows paths use
    backslashes — must be normalized first or the encoded path won't match
    the directory Claude Code creates under ~/.claude/projects/.
    """
    return cwd.replace("\\", "-").replace("/", "-").replace("_", "-")


def _find_today_transcripts(within_days: int = 1) -> list[Path]:
    """Locate Claude Code transcript files modified recently for this CWD.

    Claude Code lays out per-project transcripts at:
      ~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl
    where encoded-cwd = cwd with every '/' and '_' replaced by '-'.
    """
    try:
        proj_dir = Path.home() / ".claude" / "projects" / _encode_cwd(os.getcwd())
        if not proj_dir.exists():
            return []
        cutoff = datetime.now() - timedelta(days=within_days)
        cutoff_ts = cutoff.timestamp()
        return sorted(
            (p for p in proj_dir.glob("*.jsonl") if p.stat().st_mtime >= cutoff_ts),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return []


def _cost_from_transcripts() -> tuple[float, int]:
    """Sum compute_transcript_usage across today's transcripts. Best-effort."""
    ss = _import_stream_signal()
    if ss is None or not hasattr(ss, "compute_transcript_usage"):
        return 0.0, 0
    total_cost = 0.0
    total_toks = 0
    for path in _find_today_transcripts():
        try:
            cost, toks, _ = ss.compute_transcript_usage(str(path))
            total_cost += float(cost or 0.0)
            total_toks += int(toks or 0)
        except Exception:
            continue
    return round(total_cost, 6), total_toks


def _read_cost_tokens() -> tuple[float, int]:
    """Resolve today's cumulative cost/tokens from the best available source.

    Priority:
      1. .raven/.cache/last-signal.json — totals.{cost,tokens} written by
         stream-signal.py after compute_transcript_usage. This is the SAME
         number the Hub receives, so the local dashboard matches the Hub.
      2. Today's Claude Code transcripts — same compute_transcript_usage logic,
         reads the raw transcripts directly. Works without a Stop hook firing.
      3. .raven/.model-session.json — sum of raven_overhead + user_work buckets,
         updated by log-overhead.py / model-router.py per call.
      4. session-stats.json — cost_sent / tokens_sent (only populated after a
         successful Hub send, so usually empty in local-only mode).
    """
    # 1. Hub-mirror sidecar
    sig = _load(SIGNAL_PATH, default={})
    if isinstance(sig, dict):
        totals = sig.get("totals") or {}
        cost = float(totals.get("cost", 0.0) or 0.0)
        toks = int(totals.get("tokens", 0) or 0)
        if cost or toks:
            return cost, toks

    # 2. Walk today's transcripts directly
    cost, toks = _cost_from_transcripts()
    if cost or toks:
        return cost, toks

    # 3. Two-bucket session attribution (live, updated per model call)
    ms = _load(MODEL_SESSION, default={})
    if isinstance(ms, dict) and "raven_overhead" in ms and "user_work" in ms:
        ov = ms.get("raven_overhead") or {}
        uw = ms.get("user_work") or {}
        cost = float(ov.get("cost_usd", 0.0) or 0.0) + float(uw.get("cost_usd", 0.0) or 0.0)
        toks = int(ov.get("tokens", 0) or 0) + int(uw.get("tokens", 0) or 0)
        if cost or toks:
            return cost, toks

    # 4. session-stats sent-watermark (post-Hub-send fallback)
    stats = _load(STATS_PATH, default={})
    if isinstance(stats, dict) and stats.get("date") == date.today().isoformat():
        return float(stats.get("cost_sent", 0.0) or 0.0), int(stats.get("tokens_sent", 0) or 0)

    return 0.0, 0


def _merge_row(existing: dict | None, delta: dict, stats: dict, project: str, user: str) -> dict:
    """Build / update today's row.

    Counters from the queue are ADDED (queue may be cleared between rollups).
    Counters from session-stats are MAXed (session-stats is cumulative-for-today).
    Cost/tokens come from _read_cost_tokens() — same source the Hub gets.
    URL lists are unioned.
    """
    today = date.today().isoformat()
    row = dict(existing) if existing else {
        "date": today,
        "started_at": f"{today}T00:00:00+00:00",
        "project": project,
        "user": user,
    }
    row["project"] = project
    row["user"] = user
    row["date"] = today
    row.setdefault("started_at", f"{today}T00:00:00+00:00")

    # Additive from queue
    for k in ("pr_created", "pr_reviewed", "lines_generated", "lines_accepted",
              "mcp_ungoverned", "mcp_override"):
        row[k] = int(row.get(k, 0) or 0) + int(delta.get(k, 0) or 0)

    # Union URL lists
    for k in ("pr_created_urls", "pr_reviewed_urls"):
        prior = row.get(k) or []
        new = delta.get(k) or []
        merged = list(dict.fromkeys([*prior, *new]))  # dedupe, preserve order
        row[k] = merged

    # Cumulative-from-stats (only trust if stats.date == today)
    if stats.get("date") == today:
        row["sessions"] = max(int(row.get("sessions", 0) or 0), int(stats.get("sessions", 0) or 0))
        row["commits"] = max(int(row.get("commits", 0) or 0), int(stats.get("commits", 0) or 0))
        row["secrets_blocked"] = max(
            int(row.get("secrets_blocked", 0) or 0),
            int(stats.get("secrets_blocked", 0) or 0),
        )
        row["cve_blocked"] = max(
            int(row.get("cve_blocked", 0) or 0),
            int(stats.get("cve_blocked", 0) or 0),
        )

    # Cost / tokens — authoritative source (same as Hub)
    cost, toks = _read_cost_tokens()
    row["cost_usd"] = round(max(float(row.get("cost_usd", 0.0) or 0.0), cost), 6)
    row["tokens"]   = max(int(row.get("tokens", 0) or 0), toks)

    # Capture timestamp — surfaced by the dashboard so user can see freshness
    row["last_captured_at"] = datetime.now(timezone.utc).isoformat()

    return row


def _write_month_file(row: dict) -> Path:
    """Upsert the row into ~/RavenVault/.metrics/YYYY-MM.json by (date, project, user)."""
    VAULT_METRICS.mkdir(parents=True, exist_ok=True)
    month = row["date"][:7]
    path = VAULT_METRICS / f"{month}.json"
    data = _load(path, default={"month": month, "sessions": []})
    if "sessions" not in data or not isinstance(data["sessions"], list):
        data = {"month": month, "sessions": []}
    key = (row["date"], row.get("project"), row.get("user"))
    replaced = False
    for i, s in enumerate(data["sessions"]):
        if (s.get("date"), s.get("project"), s.get("user")) == key:
            data["sessions"][i] = row
            replaced = True
            break
    if not replaced:
        data["sessions"].append(row)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    os.replace(tmp, path)
    return path


def _mark_queue_rolled(queue: list[dict]) -> None:
    """Stamp every queue event as rolled-up so we don't re-count it."""
    if not queue:
        return
    changed = False
    for evt in queue:
        if not evt.get("_rolled_up"):
            evt["_rolled_up"] = True
            changed = True
    if changed:
        try:
            tmp = QUEUE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(queue, indent=2))
            os.replace(tmp, QUEUE_PATH)
        except Exception:
            pass  # never block — worst case we re-count once


def main() -> None:
    try:
        manifest = _load(MANIFEST_PATH, default={})
        queue = _load(QUEUE_PATH, default=[])
        if not isinstance(queue, list):
            queue = []
        stats = _load(STATS_PATH, default={})
        if not isinstance(stats, dict):
            stats = {}

        project, user = _identity(manifest)
        delta = _aggregate_unprocessed(queue)

        # Skip only when there is literally no data anywhere — no queue, no stats,
        # no sidecar, no model-session. Any of those means cost/tokens could move.
        has_data = (
            any(delta.values())
            or bool(stats)
            or SIGNAL_PATH.exists()
            or MODEL_SESSION.exists()
        )
        if not has_data:
            return

        # Find existing row for today / project / user
        today = date.today().isoformat()
        month_path = VAULT_METRICS / f"{today[:7]}.json"
        existing = None
        data = _load(month_path, default=None)
        if isinstance(data, dict):
            for s in data.get("sessions", []):
                if (s.get("date"), s.get("project"), s.get("user")) == (today, project, user):
                    existing = s
                    break

        row = _merge_row(existing, delta, stats, project, user)
        _write_month_file(row)
        _mark_queue_rolled(queue)

        # One-line confirmation so the user sees the hook fire each response.
        # Suppress with RAVEN_QUIET_ROLLUP=1 in env if it gets noisy.
        if not os.environ.get("RAVEN_QUIET_ROLLUP"):
            cost = float(row.get("cost_usd", 0.0) or 0.0)
            toks = int(row.get("tokens", 0) or 0)
            commits = int(row.get("commits", 0) or 0)
            pr_c = int(row.get("pr_created", 0) or 0)
            pr_r = int(row.get("pr_reviewed", 0) or 0)
            parts = [f"${cost:.2f}", f"{toks/1000:.0f}k tok"]
            if commits:
                parts.append(f"{commits} commit{'s' if commits != 1 else ''}")
            if pr_c:
                parts.append(f"{pr_c} PR{'s' if pr_c != 1 else ''} created")
            if pr_r:
                parts.append(f"{pr_r} reviewed")
            sys.stderr.write(
                f"🪶 Raven captured: {' · '.join(parts)}  →  ~/RavenVault/.metrics/\n"
            )
            sys.stderr.flush()
    except Exception:
        # Hook must never fail
        return


if __name__ == "__main__":
    main()
    sys.exit(0)
