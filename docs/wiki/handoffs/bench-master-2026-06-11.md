---
agent: bench-master
gap: G9
date: 2026-06-11
status: DONE
branch: gap/g9-bench
unblocks: [G10]
---

## Summary

Built the ER measurement layer: Febrl 1-4 + synthetic manufacturing datasets,
a harness that runs the REAL aryx.resolution funnel, `make er-bench` /
`make er-bench-quick` gates, 13 funnel tests, and the first measured
precision/recall rows in BENCHMARKS.md.

## Delivered

- `benchmarks/datasets/fetch.py` — Febrl loader via recordlinkage (no network)
- `benchmarks/datasets/make_mfg.py` — 10K supplier records, controlled corruption
- `benchmarks/run_bench.py` — harness: P/R/F1, blocking recall, --compare-legacy, --sweep, --quick
- `Makefile` — `er-bench` (full, appends BENCHMARKS.md) + `er-bench-quick` (<60s, parseable)
- `tests/test_resolution_funnel.py` — 12 passing + 1 xfail (G3 contract)
- `docs/wiki/BENCHMARKS.md` — first 7 measured rows
- `docs/wiki/gaps/G9.md` — full evidence

## Numbers G10 Needs

- **Adjudication band [0.90, 0.92) true-positive mass: 8.7% (Febrl1), 2.7% (mfg-10k).**
  Both >2% → current band width is justified; do NOT widen.
- **LLM ceiling:** always_accept − always_reject = +5.6pp recall (Febrl1).
  That is the maximum recall G10's adjudicator can add at current thresholds.
- **Recall ceiling:** blocking recall is 0.852 → G10's end-to-end recall
  cannot exceed that until the G2 reopen lands.
- Sweep CSV: generate with `PYTHONPATH=src python -m benchmarks.run_bench
  --dataset febrl1 --sweep` → `benchmarks/sweep_febrl1.csv`.

## Carry-forwards

- G2 reopen filed: blocking recall 0.852 < 0.95 gate
  (`handoffs/bench-master-g2-reopen-2026-06-11.md`)
- mfg-10k precision drop (0.84) at scale → scoring-stage finding for G7:
  string similarity alone cannot separate near-name distinct entities
- The xfail `test_golden_record_order_independent` flips green when G3 merges
- NC voters dataset skipped (not headlessly fetchable); Febrl 1-4 + mfg sufficient for v1
