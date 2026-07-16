---
name: raven-contribute
description: Query AI/human line attribution for files in this repo. Subcommands — who, lines, audit, attribute, signoff. Powered by .raven/state/attributions.json (local) and the Hub /api/v1/projects/.../attributions API (when reachable).
allowed-tools: Bash Read
---

# raven-contribute — Attribution Queries

Every line of source code in a Raven project has a structured attribution
record naming a human (always) and an AI model (when applicable). This skill
exposes that data through five subcommands.

## Subcommands

| Command | What it returns |
| ------- | --------------- |
| `who <file>` | Most-recent human author + top 3 contributors by line count. |
| `lines <file>:<a>-<b>` | Attribution span(s) covering the given line range. |
| `audit --model X --since Y [--csv]` | Audit-ready table (CSV by default with `--csv`). |
| `attribute <file>:<a>-<b> <email>` | Manual correction; appends superseded row. |
| `signoff <file>` | Records signoff for the file on the current commit. |

## Live project context

!`cat .raven/manifest.json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('contribute',{}); print('Project:', d.get('project'), '| Triage mode:', c.get('triage_mode','ASK'), '| Edit log:', c.get('edit_log','.raven/state/edits.jsonl'))" 2>/dev/null || echo "Project: (manifest not found — run raven-init first)"`

## How to invoke

Shell out to the CLI from any user prompt:

```
!python3 skills/raven-contribute/cli.py who src/billing/invoice.py
!python3 skills/raven-contribute/cli.py lines src/billing/invoice.py:120-154
!python3 skills/raven-contribute/cli.py audit --model claude-sonnet-4.6 --since 2026-01-01 --csv
!python3 skills/raven-contribute/cli.py attribute src/legacy.py:50-100 j.doe@giggso.com
!python3 skills/raven-contribute/cli.py signoff src/billing/invoice.py
```

`who` and `lines` work entirely from `.raven/state/attributions.json` so they
do not require Hub connectivity. `audit`, `attribute`, and `signoff` reach the
Hub through the local sync queue (offline-safe).

## Data sources

- **Local truth**: `.raven/state/attributions.json` — rebuilt every pre-commit.
- **Hub truth**: Postgres tables `projects`, `attributions`, `signoffs`, `files`, `models`, `commits` (TDD §A.5.2).
- **Per-file doc**: `docs/contribute/<file>.md` — human-readable summary; never edited by hand.

## When to invoke this skill

- On-call asks "who do I call?" → `/raven-contribute who <file>`.
- Reviewer wants line provenance → `/raven-contribute lines <file>:<a>-<b>`.
- Security officer needs audit evidence → `/raven-contribute audit ...`.
- A wrong attribution slipped in → `/raven-contribute attribute ...`.
