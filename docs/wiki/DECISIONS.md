# Decisions — append-only ADR log
<!-- Format: DEC-NNN | date | agent | decision | rationale -->

| ID | Date | Agent | Decision | Rationale |
|----|------|-------|----------|-----------|
| DEC-001 | 2026-06-11 | conductor | G10 adjudication ladder: Claude API + ChatGPT parallel → human escalation | Majority AI vote covers automated cases; human always wins on split; audit trail required for enterprise trust |
| DEC-002 | 2026-06-11 | adjudicator | Review band [0.75, 0.90); LLM band stays [0.90, 0.92); band pairs = NON-merge for the run | G9 sweep: [0.90,0.92) holds 8.7% TP mass (Febrl1) — keep; pairs in [0.60,0.90) were silently lost, now queued. Wrong-merge worse than missed-merge in audited domains. All four thresholds env-tunable (ARYX_ER_*) |
| DEC-003 | 2026-06-11 | adjudicator | LLM failure during adjudication = queue for human, never fail-open or crash the run | Fail-to-human matches G4's fail-closed posture; the pair becomes labeled data either way |
| DEC-004 | 2026-06-11 | action-architect | Action DSL: JSON with guard reusing the rules-engine `when` matcher verbatim; effects v1 = set_attribute, add_relationship, remove_relationship, set_label; Postgres-first, graph never mutated directly | One condition grammar across rules/axioms/actions is a product feature; FalkorDB is a projection (core architecture rule) |
| DEC-005 | 2026-06-11 | action-architect | MCP `act` tool ALWAYS creates a pending execution — agent-initiated mutations never auto-apply, regardless of the action's approval flag | Trust posture worth marketing: every external-agent mutation faces a human in v1 |
| DEC-006 | 2026-06-11 | confidence-smith | Cluster confidence = MIN merge-edge score, clamped [0.5, 0.99]; human edges count 0.99; singletons 0.5 | A chain is as trustworthy as its weakest merge; min not mean. Certainty (1.0) is never claimed |
