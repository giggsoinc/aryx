# Gap-Closure Program — Close-Out

All 10 tracked gaps closed (2026-06-11). G6 (relate candidates) and G14
(temporal model) were parked out of scope from day one.

## Bench history (headline rows — full table in BENCHMARKS.md)

| Milestone | Dataset | P | R | F1 | blocking_recall |
|---|---|---|---|---|---|
| Pre-G2 (legacy prefix) | febrl1 | 1.0000 | 0.5140 | 0.6790 | 0.7280 |
| Post-G2 (multi-key) | febrl1 | 1.0000 | 0.5900 | 0.7421 | 0.8520 |
| Post-G7/G10 (quick gate) | febrl1 | 1.0000 | 0.5900 | 0.7421 | 0.8520 |

G2 delta: +7.6pp recall at perfect precision. G7/G10 changed zero merges by
design — confidence is metadata, band pairs are non-merge.

## Decisions index

DEC-001 dual-LLM adjudication ladder · DEC-002 review band [0.75, 0.90) ·
DEC-003 LLM failure = fail-to-human · DEC-004 action DSL + Postgres-first ·
DEC-005 MCP act always-pending · DEC-006 weakest-link confidence.

## Open findings

- **G2 reopen** (P3): blocking recall 0.852 < 0.95 gate —
  handoffs/bench-master-g2-reopen-2026-06-11.md has root-cause candidates.
- **mfg-10k precision** 0.84 at scale: string similarity can't separate
  near-name distinct entities — embeddings/attributes must contribute (G7's
  scoring evidence, gaps/G9.md).

## Needs the live Docker stack (deploy via git, then verify)

- G8 equivalence gate (incremental vs full-rebuild graph identity)
- G1 scale row (1M records / 8GB container) + G8 10× incremental speedup row
- G10 recall-lift measurement with a real LLM adjudicator
- Migrations 0019-0023 apply on startup (idempotent; verify once)

## v2 backlog

Source-writeback effects · monitoring agents (Fabric-style) · quarterly
labeled-pair export (the aryx_adjudication moat) · adjudication + actions
UI panels · batch UNWIND projection · G6 relate candidates · G14 temporal.
