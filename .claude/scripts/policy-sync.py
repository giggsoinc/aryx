#!/usr/bin/env python3
"""
Raven Enterprise — Policy Sync
SessionStart hook. Pulls current org policy from Hub and caches locally.

If Hub is unreachable: uses cached policy. If no cache: falls back to shadow mode.
Never blocks the session. Always succeeds silently.

Flow:
  1. Read manifest to find hub_url + org
  2. GET /api/v1/policy?org=X from Hub
  3. Write to .raven/mcp-policy.json
  4. Inject policy status into additionalContext

Runs as: python3 ~/.claude/scripts/policy-sync.py
"""

import json, sys, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

MANIFEST_PATH     = Path(".raven/manifest.json")
SECRETS_PATH      = Path(".raven/manifest.secrets.json")
POLICY_CACHE_PATH = Path(".raven/mcp-policy.json")
ORG_POLICY_PATH   = Path.home() / ".raven" / "enterprise-mcp-policy.json"
SYNC_LOG_PATH     = Path(".raven/.cache/policy-sync.json")

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else (default or {})
    except Exception:
        return default or {}

def fetch_policy(hub_url: str, org: str, timeout: int = 5) -> dict | None:
    """Pull org policy from Hub. Returns None if unreachable."""
    url = hub_url.rstrip("/") + f"/api/v1/policy?org={org}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read())
    except Exception:
        pass
    return None

def write_policy(policy: dict):
    """Write merged policy to both local project + user-level cache."""
    POLICY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Flatten Hub response to mcp-policy.json format
    local_policy = {
        "mode":    policy.get("mode", "shadow"),
        "default": policy.get("mode", "shadow"),
        "allowed": policy.get("policy_json", {}).get("allowed", []),
        "blocked": policy.get("policy_json", {}).get("blocked", []),
        "_synced_at":  datetime.now(timezone.utc).isoformat(),
        "_synced_from": "hub",
        "_version": policy.get("version", 0),
    }
    POLICY_CACHE_PATH.write_text(json.dumps(local_policy, indent=2))

    # Also write MDM-style enterprise policy (highest priority, read-only intent)
    ORG_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORG_POLICY_PATH.write_text(json.dumps(local_policy, indent=2))

def log_sync(status: str, mode: str, version: int, hub_url: str):
    SYNC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_LOG_PATH.write_text(json.dumps({
        "ts":      datetime.now(timezone.utc).isoformat(),
        "status":  status,
        "mode":    mode,
        "version": version,
        "hub_url": hub_url,
    }, indent=2))

def main():
    manifest = load_json(MANIFEST_PATH)
    secrets  = load_json(SECRETS_PATH)

    hub_url = manifest.get("hub_url") or secrets.get("hub_url", "")
    org     = manifest.get("org", "")

    # No Hub configured — local-only mode, nothing to sync
    if not hub_url or not org:
        sys.exit(0)

    # Attempt Hub fetch
    policy = fetch_policy(hub_url, org)

    if policy:
        write_policy(policy)
        mode    = policy.get("mode", "shadow")
        version = policy.get("version", 0)
        log_sync("ok", mode, version, hub_url)

        # Inject policy status into session context
        allowed_count = len(policy.get("policy_json", {}).get("allowed", []))
        blocked_count = len(policy.get("policy_json", {}).get("blocked", []))

        context_line = (
            f"ORG POLICY SYNCED: mode={mode} · "
            f"{allowed_count} allowed MCPs · {blocked_count} blocked MCPs · "
            f"version={version} from {hub_url}"
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName":    "SessionStart",
                "additionalContext": context_line,
            }
        }
        print(json.dumps(output))
    else:
        # Hub unreachable — use cached policy
        cached = load_json(POLICY_CACHE_PATH)
        mode   = cached.get("mode", "shadow")
        synced = cached.get("_synced_at", "never")
        log_sync("cached", mode, cached.get("_version", 0), hub_url)

        if cached:
            context_line = (
                f"ORG POLICY: cached mode={mode} · Hub unreachable · "
                f"last synced {synced[:10]}"
            )
        else:
            context_line = (
                f"ORG POLICY: Hub unreachable, no cache — defaulting to shadow mode"
            )
        output = {
            "hookSpecificOutput": {
                "hookEventName":    "SessionStart",
                "additionalContext": context_line,
            }
        }
        print(json.dumps(output))

if __name__ == "__main__":
    main()
