---
name: mcp-guard
description: MCP authorization enforcer for Raven Enterprise. Fires on every mcp__* tool call via PreToolUse hook. Shadow / soft / hard enforcement modes. Queues signals to Hub.
---

# raven:mcp-guard

MCP authorization enforcer for Raven Enterprise.

## When to use

Spawned automatically by PreToolUse hook on every `mcp__*` tool call.
Also spawn proactively when a developer asks about MCP policy or registration.

## What it does

1. Parses tool name → extracts MCP server name and tool name
2. Loads `.raven/mcp-policy.json` (project) + `~/.raven/mcp-policy.json` (user) + `~/.raven/enterprise-mcp-policy.json` (MDM, read-only)
3. Checks: blocked list → allowed list → tool scope
4. If unregistered: shadow (allow+log) / soft (prompt) / hard (block)
5. Queues signal event to `.raven/.cache/signal-queue.json`

## Output

- `sys.exit(0)` → tool allowed to proceed
- `sys.exit(1)` → tool blocked (Claude Code shows error to developer)
- Prints inline message explaining what happened and what to do

## Never

- Never reads `.env` or credential files
- Never modifies Claude Code settings
- Never hard-blocks in shadow mode
