---
name: survivor-smith
description: "Closes G3: golden record merging. Replaces first-non-empty-wins with confidence-weighted merge, adds conflict detection, and traces provenance per attribute. Lane C — independent, no dependencies."
allowed-tools: [Bash, Read, Write, Edit]
depends_on: []
files_owned: [src/aryx/resolution/cluster.py, src/aryx/resolution/survivor.py, tests/test_survivor.py, docs/wiki/gaps/G3.md]
---

# survivor-smith — Close G3 (Golden Record)

## Wiki Protocol
Read first: `docs/wiki/STATE.md`, `docs/wiki/sources/gap_map.md` §G3, `docs/wiki/gaps/G3.md` (create if missing).
Write last: Work Log entry on G3.md + handoff block, committed WITH the code.

## Verified Baseline (do not re-derive)
- `src/aryx/resolution/cluster.py:golden_record` — first non-empty value per key, no weighting
- Contradictory values: first source wins silently (e.g. two different emails → unknown which is right)
- No attribute-level provenance: can't tell which source contributed which field
- `ResolvedEntity.attributes` is a plain `dict[str, Any]` — no confidence or source metadata

## Implementation Prompt

You are improving how Aryx merges a cluster of matched records into a single golden record. Three changes:

**1. New module `src/aryx/resolution/survivor.py`**

Implement `survivors(payloads: list[dict], record_ids: list[int], pair_scores: dict[tuple[int,int], float]) -> dict[str, Any]`:

- **Confidence-weighted merge:** for each attribute, collect (value, weight) pairs where weight = average pairwise score of the records contributing that value (use `1.0` for singletons). Pick the value with the highest total weight.
- **Conflict detection:** if two non-empty values differ for the same attribute, log a WARNING:  
  `"conflict attr=<name> values=[v1, v2] record_ids=[id1, id2] — top-weight value kept"`
- **Provenance:** return `_provenance: {attr: record_id}` as a special key in the merged dict, mapping each attribute to the record_id that contributed it.
- Signature fallback: if `pair_scores` is empty (called from legacy code), behave identically to the old `golden_record` (first-non-empty wins).

**2. Update `src/aryx/resolution/cluster.py`**
- Keep `UnionFind` unchanged.
- Keep `golden_record` as a thin shim that calls `survivors(payloads, [], {})` — preserves all existing callers.
- Add a `golden_record_weighted(payloads, record_ids, pair_scores)` function that delegates to `survivors`.

**3. Update `src/aryx/resolution/run.py`**
- In the `resolve()` function, collect pair scores during the scoring loop into a `dict[tuple[int,int], float]`.
- When building the entity, call `golden_record_weighted(payloads, member_ids, pair_scores)` instead of `golden_record`.
- Strip `_provenance` from `entity.attributes` before saving — store it as `entity.provenance` (add this field to `ResolvedEntity` model, default `None`).

**4. Update `src/aryx/models.py` (if needed)**
- Add `provenance: dict[str, int] | None = None` to `ResolvedEntity`.

**5. Tests — `tests/test_survivor.py`:**
- Weighted merge: record with higher pairwise score wins over singleton with different value
- Conflict logged: two records with different emails → WARNING emitted, one value kept
- Provenance present: `_provenance` maps each attr to a record_id
- Legacy fallback: `golden_record([p1, p2])` still returns first-non-empty (regression)
- Single-record cluster: attributes pass through unchanged, provenance maps each attr to the one record_id

**Constraints:**
- No new pip dependencies.
- Keep every module ≤150 lines.
- Type hints + docstrings per house style.
- Run `PYTHONPATH=src python -m pytest tests/test_survivor.py -v` to confirm before handoff.

## Acceptance Gates
- Full suite green including new test_survivor.py (≥5 new tests).
- `python -c "from aryx.resolution.survivor import survivors; print(survivors([{'a':1},{'a':2}],[1,2],{(1,2):0.95}))"` runs without error.
- Conflict test: two records with differing `email` attribute → WARNING in logs, one value in output.

## Handoff
Write `docs/wiki/handoffs/survivor-smith-<date>.md` per WIKI_SCHEMA.md.
`unblocks: []` (G3 is independent; G10 adjudication display benefits from provenance but doesn't hard-depend)
Warnings: "provenance field added to ResolvedEntity — entity_store.save() should persist it; parked for now, logged at DEBUG"
