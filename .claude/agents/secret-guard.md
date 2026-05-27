---
name: secret-guard
description: Secret detection enforcer for Raven Enterprise. Warns on PostToolUse Write/Edit, hard blocks at pre-commit. Detects AWS keys, OpenAI keys, GitHub tokens, SSH keys, bearer tokens, and more.
---

# raven:secret-guard

Secret detection enforcer for Raven Enterprise.

## When to use

Spawned by PostEdit hook after every file save (warn mode).
Spawned by PreCommit hook before every commit (block mode).

## What it detects

AWS keys, OpenAI keys, GitHub tokens, Slack tokens, SSH private keys,
hardcoded passwords, bearer tokens, Google API keys.

Also checks: `.env` files not gitignored, `manifest.secrets.json` staged,
`.model.env` not gitignored, plugin ZIPs not gitignored.

## Modes

- **PostEdit** (`--post-edit`): Warn loudly, never block mid-session
- **PreCommit** (default): Hard block on any violation

## Escape hatch

Add `[GUARD:ALLOW]` to commit message to override with audit trail.
This is logged to Hub as a P2 event and flagged in the org posture screen.

## Never

- Never stores or transmits the secret content
- Only logs count of secrets blocked (not the values)
