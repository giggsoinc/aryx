# Insight & Visualization Quality — What's Been Tested

Tracks real experiments run against the live system to answer: *why do
generated dashboard specs (C08) come out thin/primitive, and what actually
helps?* Every entry below was tested against the real pipeline (real LLM
calls, real C09 validation) — nothing here is a guess.

## Summary

| # | Experiment | Result | Kept? |
|---|---|---|---|
| 1 | `reasoning_effort="medium"` (vs `"low"`) on `gpt-oss-20b` | Fixed empty completions, but worse rejection rate + 4-8x latency | ❌ Reverted |
| 2 | Prompt instruction: justify each KPI's business relevance | Zero compliance across test runs | ❌ Reverted |
| 3 | Richness indicator (KPI/analysis/viz/assumption-depth signal in UI) | Makes thinness visible; doesn't fix it | ✅ Kept |
| 4 | `missing_measure` / `missing_filter_value` C09 checks | Catches a real, previously-silent defect class (fabricated 0.0 / null values) | ✅ Kept |
| 5 | Model: `llama-3.3-70b-versatile` | Produces valid, richer specs reliably | ✅ Works |
| 6 | Model: `openai/gpt-oss-120b` | Calls succeed, but repeatedly produces incoherent ratio-KPI filters (caught by #4, not fixed) | ⚠️ Unreliable |
| 7 | Model: `groq/compound` | Fails outright — request too large (413) for whole-workspace prompts | ❌ Doesn't work here |
| 8 | Model: `qwen/qwen3.6-27b` | Fails outright — empty completion (same failure mode as original `gpt-oss-20b` bug, needs its own reasoning-budget accommodation) | ❌ Doesn't work here |

## Root cause framing (Ishikawa)

Three candidate causes for "primitive" output, before testing:
- **Machine**: reasoning effort / token budget tradeoffs on the LLM call.
- **Method**: the prompt asks for volume, not justification.
- **Measurement**: nothing scored richness after generation — C09 only checks
  structural correctness.

## 1 — `reasoning_effort` A/B (Machine)

Real test, 5 calls each, same workspace/objective, `gpt-oss-20b`:

| | `low` (baseline) | `medium` |
|---|---|---|
| valid | 2/5 | 3/5 |
| controlled_failure (C09 rejected) | 1/5 | 2/5 ⚠️ |
| llm_call_failed (empty completion) | 2/5 (40%) | 0/5 (0%) ✅ |
| latency | ~10–20s | 79–85s+, one run exceeded 5 min |

**Verdict:** reverted to `low`. `medium` fixed the empty-completion problem but
made rejection rate worse and latency risky, with no reliable richness gain.
Rollback rule (set *before* testing): any rejection-rate increase → revert,
no debate.

## 2 — Business-justification prompt instruction (Method)

Added an instruction asking the model to state, per KPI, *why* it serves the
objective — not just how it's computed (`prompt.py` discipline #4a, briefly
shipped as `PROMPT_VERSION 1.4`).

Real test, 5 calls: 2/5 valid, and **0 of 2** valid runs contained any
business-justification-style assumption — the model ignored the instruction
entirely, kept writing data caveats instead ("dataset contains all necessary
columns").

**Verdict:** reverted to `PROMPT_VERSION 1.3`. Zero compliance, not worth the
added prompt length/complexity.

## 3 — Richness indicator (Measurement)

Frontend-only addition (`DashboardSpecPanel.tsx`): shows KPI/analysis/
visualization counts + a substantive-vs-total assumptions ratio, flagged
amber below a threshold (<3 KPIs, <4 visualizations, or zero substantive
assumptions). Never blocks or rejects — C09 still owns correctness.

**Verdict:** kept. Doesn't fix the underlying behavior, but for the first
time makes "this spec came out thin" visible without a human reading it.

## 4 — Real correctness bugs found and fixed along the way

Not richness fixes per se, but directly relevant: two defect classes where a
structurally-valid-but-semantically-empty field silently produced a wrong
result instead of failing loudly.

- **`missing_measure`**: a sum/average/median KPI with no `measure` field
  compiled against a literal empty column name, returning a fabricated
  `value=0.0` instead of a real number or a rejection.
- **`missing_filter_value`**: a `KpiFilter` with a `column` but no
  `value`/`values` compiled to `filter_equals(column, None)`, matching zero
  real rows — silently zeroing out whatever KPI/analysis depended on it.
  Found live in Workspace7 (`llama-3.3-70b-versatile` produced exactly this;
  later independently reproduced by `openai/gpt-oss-120b` too, confirming the
  fix generalizes across models).

Both now: dropped at grounding (`ground.py`, warn not invent) and promoted to
a hard C09 rejection, with a repair instruction specific enough that the one
allowed retry has a real chance of fixing it.

## 5-8 — Model comparison (live, real calls against Workspace7)

| Model | Outcome |
|---|---|
| `llama-3.3-70b-versatile` | ✅ Produces valid specs reliably (multiple confirmed runs) |
| `openai/gpt-oss-20b` | ⚠️ Original default; frequent empty completions until `max_tokens`/`reasoning_effort="low"` fix; daily token quota is easy to exhaust (this session hit the 200k/day cap) |
| `openai/gpt-oss-120b` | ⚠️ Calls succeed, no quota/size issues, but repeatedly proposes ratio-KPI filters with no value — correctly rejected by fix #4, never produced a valid spec in testing |
| `groq/compound` | ❌ HTTP 413 request_too_large — Groq's agentic/tool-orchestration system has a much smaller max request size than a plain chat model; whole-workspace prompts don't fit |
| `qwen/qwen3.6-27b` | ❌ HTTP 400 json_validate_failed, empty `failed_generation` — same "hidden-reasoning model exhausts its budget before emitting JSON" failure as the original `gpt-oss-20b` bug; the current `reasoning_effort` accommodation in `llm_providers.py` only fires for `"gpt-oss"` in the model name, not Qwen |

## Bottom line

No cheap lever found that makes a small/cheap model reason more deeply about
*relevance* while staying reliable — both direct attempts (effort tuning,
justification prompting) were tested for real and failed. What actually
moved the needle was correctness enforcement (catching silently-wrong
results) and observability (the richness indicator), not smarter prompting.
`llama-3.3-70b-versatile` is the only model tested so far that reliably
produces a valid, reasonably rich spec end to end.

## Open items

- `qwen/qwen3.6-27b` (and possibly other Groq-hosted reasoning models) would
  need their own reasoning-budget parameter identified and added to
  `llm_providers.py` — don't guess at the parameter name, confirm it first.
- `groq/compound` might still work for single-dataset (not whole-workspace)
  prompts, given its smaller size limit — untested.
- The Analysis Execution / Dashboard Composition buttons are hard-coded to
  workspace scope only (separate, still-open issue — a spec generated for a
  single dataset never reaches execution).
