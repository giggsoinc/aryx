---
name: raven-enterprise
description: Raven Enterprise v3.0 — governance and intelligence layer for Claude Code at scale. Guards active, signals flowing to Hub (if configured). MCP guard, model routing, Hub telemetry, SAML/OIDC auth.
---

# Raven Enterprise v3.0

Governance and intelligence layer for Claude Code at scale.
Guards active on this machine. Signals flowing to Hub (if configured).

---

## What's running on this machine

| Guard | Hook | Mode |
|---|---|---|
| MCP Guard | PreToolUse | shadow / soft / hard (check `.raven/mcp-policy.json`) |
| Secret Scan | PostEdit + PreCommit | warn on edit, hard block on commit |
| CVE Gate | PreCommit | hard block CVSS > 7, approval flow otherwise |
| Signal Emitter | PostSession | 200-byte daily summary → Hub |

---

## Setup commands

**First time on this repo:**
```bash
bash agent/raven-init.sh --hub-url https://raven.yourcompany.com --org yourorg
```

**Discover available models:**
```bash
python3 .claude/scripts/model-discover.py
```

**Check model routing:**
```bash
python3 .claude/scripts/model-router.py --task medium --explain
```

**Check MCP policy:**
```bash
cat .raven/mcp-policy.json
```

---

## MCP governance

Current mode is set in `.raven/mcp-policy.json → mode`.

| Mode | Behaviour |
|---|---|
| `shadow` | All MCPs run. Unregistered ones logged. |
| `soft` | First-use prompt for unregistered MCPs. 10s auto-continue. |
| `hard` | Unregistered MCPs blocked. Policy must cover all MCPs. |

To register a new MCP in shadow/soft mode: pick **Always** at the first-use prompt.
To change mode org-wide: update via Hub policy management screen.

---

## Secret scan

Runs on every file save (warn only) and every commit (hard block).
Patterns: AWS keys, OpenAI keys, GitHub tokens, Slack tokens, private keys, hardcoded passwords, bearer tokens.

If a secret is detected at commit: fix the file, then re-commit.
Intentional exception: add `[GUARD:ALLOW]` to commit message (logged to Hub).

---

## CVE gate

Runs at commit on every Python import in staged files.
- **Tier 1** (org whitelist: fastapi, requests, boto3, sqlalchemy, etc.) → auto-approved
- **Tier 2** (category whitelist: testing, HTTP clients, etc.) → auto-approved
- **Tier 3** (unknown) → GPT CVE analysis → hard block if CVSS > 7

Set `OPENAI_API_KEY` in shell env to enable Tier 3 analysis.

---

## Model routing

Reads `.model.env` (gitignored). Routes each task to cheapest adequate model.

| Tier | Examples | Default |
|---|---|---|
| LOCAL_ONLY | grep, rename, format | Ollama if available |
| SIMPLE | boilerplate, test stubs | Haiku / Groq Llama |
| MEDIUM | new features, review | Sonnet / Gemini Pro |
| COMPLEX | architecture, refactor | Sonnet / GPT-4o |

Opus is never used by default. Only when you explicitly ask.

---

## Hub connection

Hub URL is set in `.raven/manifest.json → hub_url`.
If blank: local-only mode — no signals sent, no org risk score computed.

To connect to Hub: update manifest and the agent will pick it up next session.

---

## Troubleshooting

**MCP blocked unexpectedly:**
Check `.raven/mcp-policy.json` mode. If `hard`, add the MCP to the allowed list.

**Secret scan false positive:**
Add `# raven-ignore` comment on the line, or use `[GUARD:ALLOW]` in commit message.

**CVE gate blocking a known-safe library:**
Add the library name to `ORG_WHITELIST_TIER1` in `cve-check.py`, or use `[GUARD:ALLOW-CVE]` in commit message.

**Signal not reaching Hub:**
Check Hub URL in manifest. Run `python3 .claude/scripts/stream-signal.py` manually to see the error.
Signals queue locally at `.raven/.cache/signal-queue.json` until Hub is reachable.

---

*Raven Enterprise v1.0.0 · Commercial · [giggso.com/raven-enterprise](https://giggso.com/raven-enterprise)*
