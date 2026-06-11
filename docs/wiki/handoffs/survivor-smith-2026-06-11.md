---
agent: survivor-smith
gap: G3
date: 2026-06-11
status: DONE
branch: aryx-g3-golden
---

## Summary

Replaced flat first-non-empty merge with confidence-weighted golden-record merge. Pair scores from the scoring stage now inform which source record's attribute value survives.

## Delivered

- `src/aryx/resolution/survivor.py` — `survivors()` with weighted merge, conflict WARNING, `_provenance` map
- `src/aryx/resolution/cluster.py` — shims for backward-compat `golden_record()`; new `golden_record_weighted()`
- `src/aryx/resolution/run.py` — collects `pair_scores`; calls weighted merge; threads `_provenance` to entity
- `src/aryx/models.py` — `ResolvedEntity.provenance: dict[str, int] | None`
- `tests/test_survivor.py` — 7 tests, all passing

## Verification

```
PYTHONPATH=src python -m pytest tests/test_survivor.py -v
# 7 passed
```

## Carry-forwards

- Conflict resolution policy is currently WARNING-only; a future gap could expose a per-workspace conflict-resolution strategy (e.g. prefer most-recent by `source.record_id`)
