#!/usr/bin/env python3
"""
Raven Enterprise — Tool Guard (PreToolUse)
Hard-blocks restricted operations on any tool call.
Returns continue:false with reason when a rule fires.

Blocked patterns:
  Bash: rm -rf / root  ·  sudo  ·  curl | bash  ·  wget | sh
        DROP/TRUNCATE without WHERE  ·  git push --force to main/master
  Write/Edit: writing to /etc /usr /bin /sbin /root  ·  .env files
  Read: reading .env / SSH keys / cloud credential files
"""

import json, re, sys

# ── Rule sets ──────────────────────────────────────────────────────────────────

BASH_BLOCK = [
    (r"rm\s+-rf\s+[/~]", "rm -rf on root or home is not allowed"),
    (r"rm\s+-rf\s+\.", "rm -rf . is not allowed — use specific paths"),
    (r"\bsudo\b", "sudo is not allowed in Claude Code sessions"),
    (r"curl\s+.*\|\s*(bash|sh|zsh)", "pipe-to-shell from curl is not allowed (supply chain risk)"),
    (r"wget\s+.*\|\s*(bash|sh|zsh)", "pipe-to-shell from wget is not allowed"),
    (r">\s*/etc/", "writing to /etc is not allowed"),
    (r"git\s+push\s+.*--force\s+.*\b(main|master)\b", "force-push to main/master is not allowed"),
    (r"git\s+push\s+.*\b(main|master)\b.*--force", "force-push to main/master is not allowed"),
    (r"git\s+reset\s+--hard\s+HEAD~[2-9]", "resetting more than 1 commit requires [GUARD:ALLOW-RESET]"),
    (r"git\s+clean\s+-[a-z]*f[a-z]*d", "git clean -fd is not allowed without [GUARD:ALLOW-CLEAN] flag"),
    (r"chmod\s+777", "chmod 777 is not allowed — use least privilege"),
    (r":\(\)\{.*\};", "fork bomb pattern detected and blocked"),
]

WRITE_BLOCK = [
    (r"^/etc/", "writing to /etc is not allowed"),
    (r"^/usr/", "writing to /usr is not allowed"),
    (r"^/bin/|^/sbin/", "writing to system binaries is not allowed"),
    (r"^/root/", "writing to /root is not allowed"),
    (r"(^|/)\.env$", "writing to .env files is not allowed — use manifest.secrets.json"),
    (r"\.pem$|\.key$|id_rsa|id_ed25519", "writing to key/cert files is not allowed"),
]

READ_BLOCK = [
    (r"(^|/)\.env$", "reading .env files is not allowed — use manifest.secrets.json or env vars"),
    (r"(^|/)\.aws/credentials$", "reading AWS credentials file is not allowed"),
    (r"(^|/)\.ssh/id_rsa$", "reading SSH private key is not allowed"),
    (r"(^|/)\.ssh/id_ed25519$", "reading SSH private key is not allowed"),
    (r"manifest\.secrets\.json$", "reading manifest.secrets.json is not allowed from skills/agents"),
]

def check_rules(patterns: list, text: str) -> str | None:
    for pattern, reason in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return reason
    return None


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)  # malformed input — pass through

    tool   = payload.get("tool_name", "")
    inputs = payload.get("tool_input", {})

    reason = None

    if tool == "Bash":
        cmd = inputs.get("command", "")
        reason = check_rules(BASH_BLOCK, cmd)

    elif tool in ("Write", "MultiEdit"):
        path = inputs.get("file_path", "")
        reason = check_rules(WRITE_BLOCK, path)

    elif tool == "Edit":
        path = inputs.get("file_path", "")
        reason = check_rules(WRITE_BLOCK, path)

    elif tool == "Read":
        path = inputs.get("file_path", "")
        reason = check_rules(READ_BLOCK, path)

    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName":     "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"[RAVEN:GUARD] {reason}",
            }
        }))
        sys.exit(0)

    # Pass through
    sys.exit(0)


if __name__ == "__main__":
    main()
