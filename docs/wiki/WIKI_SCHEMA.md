# Aryx Gap-Closure Wiki — Schema & State Protocol

> The Karpathy LLM-Wiki layer for this program. Every agent reads this file first.
> Pattern: immutable sources, LLM-owned wiki pages, git as the version/lock layer.
> Knowledge compounds — no agent ever rediscovers what another agent already proved.

## Directory Layout (lives in the Aryx repo)

```
docs/wiki/
├── STATE.md            # Machine-readable status board. THE dispatch source of truth.
├── DECISIONS.md        # Append-only ADR log. Never edited, only appended.
├── BENCHMARKS.md       # ER precision/recall history. The compounding sales asset.
├── gaps/
│   ├── G4.md … G13.md  # One page per gap. Owned by that gap's agent.
├── handoffs/
│   └── <agent>-<date>.md   # Structured handoff blocks (schema below)
└── sources/            # IMMUTABLE: gap_map.md, benchmark datasets notes, vendor docs
```

## Ownership Rules (strict)

1. `sources/` is read-only for all agents. Ground truth. Re-derivable.
2. Each `gaps/G*.md` page is owned by exactly one agent. Others read, never write.
3. `STATE.md` is written ONLY by the Orchestrator. Gap agents request changes via handoff blocks.
4. `DECISIONS.md` and `BENCHMARKS.md` are append-only. Any agent may append; none may edit history.
5. Every wiki write is committed in the SAME git commit as its related code change. State and code never drift.

## STATE.md Template

```markdown
# Program State — updated by Orchestrator only
| Gap | Agent | Status | Branch | Blocked-by | Last-commit | Bench-P/R |
|-----|-------|--------|--------|------------|-------------|-----------|
| G4  | auth-warden    | DONE        | gap/g4-auth   | —     | abc1234 | n/a |
| G2  | block-smith    | IN_PROGRESS | gap/g2-block  | —     | def5678 | n/a |
| G9  | bench-master   | READY       | —             | G2    | —       | —   |
| G3  | survivor-smith | READY       | —             | —     | —       | n/a |
| G10 | adjudicator    | BLOCKED     | —             | G2,G9 | —       | —   |
| G1+G5 | stream-scaler| BLOCKED     | —             | G2    | —       | —   |
| G12 | pool-fitter    | READY       | —             | —     | —       | n/a |
| G7  | confidence-smith| BLOCKED    | —             | G2    | —       | —   |
| G8  | projector      | BLOCKED     | —             | G1    | —       | —   |
| G13 | action-architect| BLOCKED    | —             | G10   | —       | —   |
Statuses: READY | IN_PROGRESS | REVIEW | DONE | BLOCKED | FAILED
```

## Gap Page Template (`gaps/G*.md`)

```markdown
# G<N> — <title>
**Agent:** <name> · **Status:** <status> · **Branch:** gap/<slug>
## Verified Baseline (from gap_map.md, never re-derive)
<file:line citations copied from sources/gap_map.md>
## Work Log (append-only, newest first)
- 2026-06-12: <what changed, commit sha, why>
## Open Questions → answered inline when resolved, never deleted
## Evidence (test output, bench numbers, file diffs)
```

## Handoff Block Schema (`handoffs/`)

```yaml
agent: block-smith
gap: G2
status: DONE
commit: <sha>
files_touched: [src/aryx/resolution/classical.py, src/aryx/resolution/blocking.py, tests/test_blocking.py]
acceptance: {tests: 41/41 pass, bench: "see BENCHMARKS.md 2026-06-13"}
unblocks: [G9, G10, G7, G1+G5]
decisions_appended: [DEC-007, DEC-008]
warnings: ["block-size cap default=5000 — tune after G9 measures real skew"]
next_agent_must_read: [gaps/G2.md#evidence]
```

## Why this beats context-passing at scale
- **Compounding:** G9's benchmark numbers persist in BENCHMARKS.md; every later agent cites measured truth, not estimates.
- **Parallel-safe:** agents work in separate git worktrees on `gap/*` branches; the wiki page-ownership rule means zero write conflicts; STATE.md merges are Orchestrator-only.
- **Auditable:** `git log docs/wiki/` IS the program history. No external tracker needed.
- **Restartable:** any agent killed mid-task resumes by reading its own gap page Work Log — the wiki is the checkpoint.
