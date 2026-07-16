# ML Skill Coordination — Handoff Protocol

Version: 1.0 · Defines how ml-specialist, aiml-specialist, and ml-ops-specialist coordinate.

---

## The Rule

**ml-specialist is always the entry point and session lead.** It owns the pipeline from
S0 to S10. It explicitly hands off to the other specialists at defined stages and hands
back at the end of each handoff.

No specialist runs independently. ml-specialist maintains the ML Plan as it accumulates cards.

---

## Handoff Map

| Stage | Hand off to | Hand back when |
|---|---|---|
| S4 — Algorithm Classes | **aiml-specialist** | Candidate set with tradeoffs is presented and HITL gate approved |
| S5 — Architecture | **aiml-specialist** | Architecture Card is complete and HITL gate approved |
| S8 — Deployment Architecture | **ml-ops-specialist** | Deployment Card is complete and HITL gate approved |
| S9 — Monitoring + Lifecycle | **ml-ops-specialist** | Lifecycle Card is complete and HITL gate approved |

---

## Handoff Format

When ml-specialist hands off:

```
→ HANDOFF TO aiml-specialist (S4 — Algorithm Classes)
   Context: {problem type from S1} + {data shape from S2} + {metric from S3}
   Instruction: Present ≥ 3 algorithm candidates with cost/latency/interpretability/data tradeoffs.
   HITL gate required before advancing to S5.
```

When a specialist hands back:

```
← HANDOFF BACK TO ml-specialist
   Completed: {stage name}
   Output: {card name — status: approved/modified/deferred}
   Next stage: {S number}
```

---

## Inline Documentation Rule (applied to all ML skill files)

Every function, method, or stage block must have an inline comment explaining:
- **What** it does (one line)
- **Why** this approach was chosen (one line if non-obvious)
- **What breaks** if skipped (one line for gates)

Example in SKILL.md stage blocks:

```
### S2 — Data Audit
# What: Gather facts about the data before any algorithm decision.
# Why: Algorithm selection is meaningless without knowing volume, labels, and privacy class.
# What breaks if skipped: Algorithm chosen for wrong data size/type — wasted compute or wrong model class.
```

This applies to all SKILL.md, FRAMEWORK.md, ALGORITHMS.md, LIFECYCLE.md, and DEPLOYMENT.md files.

---

## Session State

ml-specialist tracks the following across the session:

```
Session State
─────────────────────────────────────────────
Problem statement:  {from S0}
Problem type:       {from S1}
Current stage:      S{N}
Cards completed:    {list}
Cards pending:      {list}
HITL gates passed:  {list}
Active specialist:  ml-specialist / aiml-specialist / ml-ops-specialist
─────────────────────────────────────────────
```

This state is printed at the start of each new response so the user always knows
where in the pipeline they are.

---

## End of Session

After S10 HITL gate is approved, ml-specialist:
1. Assembles all cards into the ML Plan template (from CARDS.md)
2. Saves to `.raven/ml-plans/{YYYY-MM-DD}-{topic-slug}.md`
3. Prints the file path and a one-line summary

```
✅ ML Plan saved: .raven/ml-plans/2026-06-07-ticket-classifier.md
   Problem: Classify support tickets into 8 categories
   Algorithm: Fine-tuned SetFit (approved S4)
   Deployment: Headless API — FastAPI (approved S8)
   Risk level: Low (Privacy: PII present, mitigated by redaction pipeline)
```
