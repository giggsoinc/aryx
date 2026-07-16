#!/usr/bin/env python3
"""
Raven Enterprise — MCP Guard
Fires on PreToolUse hook. Enforces org MCP policy.

Modes (set in .raven/mcp-policy.json → "mode"):
  shadow  — unknown MCPs run, logged as unregistered (default)
  soft    — unknown MCPs show first-use prompt, auto-continue 10s
  hard    — unknown MCPs blocked unless [MCP:ALLOW] in session

Never blocks on day 1. Shadow mode is always the starting point.
Every override is tracked in the daily signal sent to Hub.
"""

import json, os, sys, time, hashlib
from pathlib import Path
from datetime import datetime, timezone

# Windows: reconfigure stdout/stderr to UTF-8 so emoji in print() don't crash
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Config ────────────────────────────────────────────────────────────────────

POLICY_PATHS = [
    Path(".raven/mcp-policy.json"),
    Path.home() / ".raven" / "mcp-policy.json",
    Path.home() / ".raven" / "enterprise-mcp-policy.json",   # MDM-pushed, read-only
]

SESSION_OVERRIDES_PATH = Path(".raven/.cache/mcp-session-overrides.json")
SIGNAL_QUEUE_PATH      = Path(".raven/.cache/signal-queue.json")

PROMPT_TIMEOUT_SECONDS = 10

# ── Policy loading ─────────────────────────────────────────────────────────────

def load_policy() -> dict:
    """Load MCP policy. Enterprise policy (MDM-pushed) is the floor."""
    merged = {"mode": "shadow", "default": "shadow", "allowed": [], "blocked": []}
    for path in reversed(POLICY_PATHS):          # enterprise last = highest priority
        if path.exists():
            try:
                p = json.loads(path.read_text())
                merged["mode"]    = p.get("mode",    merged["mode"])
                merged["default"] = p.get("default", merged["default"])
                # merge allowed lists — enterprise entries cannot be removed by user policy
                for entry in p.get("allowed", []):
                    existing = next((a for a in merged["allowed"] if a["name"] == entry["name"]), None)
                    if existing:
                        existing.update(entry)
                    else:
                        merged["allowed"].append(entry)
                for name in p.get("blocked", []):
                    if name not in merged["blocked"]:
                        merged["blocked"].append(name)
            except Exception:
                pass
    return merged

# ── Session overrides (A/S/N choices persist for session) ────────────────────

def load_session_overrides() -> dict:
    SESSION_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SESSION_OVERRIDES_PATH.exists():
        try:
            return json.loads(SESSION_OVERRIDES_PATH.read_text())
        except Exception:
            pass
    return {}

def save_session_override(mcp_name: str, choice: str):
    overrides = load_session_overrides()
    overrides[mcp_name] = {"choice": choice, "ts": datetime.now(timezone.utc).isoformat()}
    SESSION_OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2))

# ── Signal queue (flushed to Hub by stream-signal.py) ───────────────────────

def queue_signal(event: dict):
    SIGNAL_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    queue = []
    if SIGNAL_QUEUE_PATH.exists():
        try:
            queue = json.loads(SIGNAL_QUEUE_PATH.read_text())
        except Exception:
            pass
    queue.append(event)
    SIGNAL_QUEUE_PATH.write_text(json.dumps(queue, indent=2))

# ── Core guard logic ──────────────────────────────────────────────────────────

def extract_mcp_name(tool_name: str) -> tuple[str, str]:
    """mcp__gmail__create_draft → ('gmail', 'create_draft')"""
    parts = tool_name.split("__")
    if len(parts) >= 3 and parts[0] == "mcp":
        return parts[1].lower(), "__".join(parts[2:]).lower()
    return None, None

def find_policy_entry(mcp_name: str, policy: dict) -> dict | None:
    for entry in policy.get("allowed", []):
        if entry.get("name", "").lower() == mcp_name:
            return entry
    return None

def tool_allowed(tool_name: str, entry: dict) -> bool:
    """Check if specific tool is in the allowed scope for this MCP."""
    tools = entry.get("tools", "*")
    if tools == "*":
        return True
    return tool_name.lower() in [t.lower() for t in tools]

def prompt_user(mcp_name: str, tool_name: str) -> str:
    """
    First-use inline prompt. Returns: 'always' | 'session' | 'never' | 'timeout'.
    Auto-continues as 'session' after PROMPT_TIMEOUT_SECONDS.
    Cross-platform: uses threading instead of select.select().
    """
    import threading
    print(f"\n🟡 MCP not in policy: {mcp_name} / {tool_name}", flush=True)
    print(f"   Add to policy?", flush=True)
    print(f"   [A] Always allow  [S] Session only  [N] Never  [?] What is this?", flush=True)
    print(f"   (auto-continues in {PROMPT_TIMEOUT_SECONDS}s → session only)", flush=True)

    result = [None]

    def _read():
        while result[0] is None:
            line = sys.stdin.readline().strip().upper()
            if line in ("A", "ALWAYS"):
                result[0] = "always"; return
            if line in ("S", "SESSION"):
                result[0] = "session"; return
            if line in ("N", "NEVER"):
                result[0] = "never"; return
            if line in ("?", "HELP"):
                print(f"\n   '{mcp_name}' is an MCP server providing tool '{tool_name}'.", flush=True)
                print(f"   MCPs can read files, call APIs, or access external services.", flush=True)
                print(f"   Check your .mcp.json or Claude settings to see how it's configured.", flush=True)
                print(f"   [A] Always allow  [S] Session only  [N] Never", flush=True)

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(PROMPT_TIMEOUT_SECONDS)
    return result[0] or "timeout"   # auto-continue as session-only

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Claude Code passes tool info via stdin as JSON on PreToolUse
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", os.environ.get("CLAUDE_TOOL_NAME", ""))
    if not tool_name:
        sys.exit(0)   # not a tool call we recognise — pass through

    mcp_name, mcp_tool = extract_mcp_name(tool_name)
    if not mcp_name:
        sys.exit(0)   # not an MCP tool — built-in Claude tool, pass through

    policy   = load_policy()
    mode     = policy.get("mode", "shadow")
    blocked  = policy.get("blocked", [])
    entry    = find_policy_entry(mcp_name, policy)
    overrides = load_session_overrides()
    session_choice = overrides.get(mcp_name, {}).get("choice")

    ts = datetime.now(timezone.utc).isoformat()
    event = {
        "ts":          ts,
        "event_type":  "mcp_call",
        "mcp_name":    mcp_name,
        "tool_name":   mcp_tool,
        "mode":        mode,
    }

    # 1. Always-blocked MCPs (enterprise hard rule)
    if mcp_name in blocked:
        print(f"🚫 MCP BLOCKED: {mcp_name} is on the org blocked list.", file=sys.stderr)
        event.update({"registered": False, "action": "blocked", "reason": "org_blocked"})
        queue_signal(event)
        sys.exit(1)

    # 2. Registered and tool in scope
    if entry:
        if tool_allowed(mcp_tool, entry):
            event.update({"registered": True, "action": "allowed", "override": None})
            queue_signal(event)
            sys.exit(0)
        else:
            # MCP registered but this specific tool is not in scope
            print(f"⚠️  MCP scope violation: {mcp_name}/{mcp_tool} not in approved tool list.", file=sys.stderr)
            event.update({"registered": True, "action": "blocked", "reason": "tool_not_in_scope"})
            queue_signal(event)
            if mode == "hard":
                sys.exit(1)
            # shadow/soft: warn but allow — use a fresh copy so the queued
            # "blocked" event is not mutated into a second conflicting entry
            allowed_event = {**event, "action": "allowed", "reason": "shadow_override"}
            queue_signal(allowed_event)
            sys.exit(0)

    # 3. Unregistered MCP — mode determines behaviour
    event["registered"] = False

    # Check session-level prior choice
    if session_choice == "always":
        event.update({"action": "allowed", "override": "always"})
        queue_signal(event)
        sys.exit(0)

    if session_choice == "session":
        event.update({"action": "allowed", "override": "session"})
        queue_signal(event)
        sys.exit(0)

    if session_choice == "never":
        event.update({"action": "blocked", "override": "never"})
        queue_signal(event)
        sys.exit(1)

    if mode == "shadow":
        # Run and log. No prompt.
        print(f"🟡 {mcp_name}/{mcp_tool} — unregistered MCP, running in shadow mode.", flush=True)
        event.update({"action": "allowed", "override": "shadow-auto"})
        queue_signal(event)
        sys.exit(0)

    if mode == "soft":
        # First-use prompt with auto-continue
        choice = prompt_user(mcp_name, mcp_tool)
        if choice == "never":
            save_session_override(mcp_name, "never")
            event.update({"action": "blocked", "override": "never"})
            queue_signal(event)
            sys.exit(1)
        if choice == "always":
            save_session_override(mcp_name, "always")
            # Also write to project policy for persistence
            _register_mcp(mcp_name, policy)
        else:
            save_session_override(mcp_name, "session")
        event.update({"action": "allowed", "override": choice})
        queue_signal(event)
        sys.exit(0)

    if mode == "hard":
        print(f"🚫 MCP BLOCKED: {mcp_name} not in org policy. Contact your admin to register it.", file=sys.stderr)
        event.update({"action": "blocked", "override": None, "reason": "hard_mode_unregistered"})
        queue_signal(event)
        sys.exit(1)

    sys.exit(0)

def _register_mcp(mcp_name: str, current_policy: dict):
    """Write MCP to project policy file when user picks 'Always'."""
    policy_path = Path(".raven/mcp-policy.json")
    if not policy_path.exists():
        return
    try:
        p = json.loads(policy_path.read_text())
        existing = [a for a in p.get("allowed", []) if a.get("name") != mcp_name]
        existing.append({"name": mcp_name, "tools": "*", "registered_by": "user", "ts": datetime.now(timezone.utc).isoformat()})
        p["allowed"] = existing
        policy_path.write_text(json.dumps(p, indent=2))
        print(f"✅ {mcp_name} added to .raven/mcp-policy.json", flush=True)
    except Exception:
        pass

if __name__ == "__main__":
    main()
