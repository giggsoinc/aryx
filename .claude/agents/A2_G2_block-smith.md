---
name: block-smith
description: "Closes G2: naive blocking. Replaces first-4-char prefix blocking with multi-key (prefix + token-set + Soundex) strategy, adds block-size cap, and seeds the benchmark fixture. Lane B critical path — G9, G10, G7, G1+G5 all block on this."
allowed-tools: [Bash, Read, Write, Edit]
depends_on: []
files_owned: [src/aryx/resolution/classical.py, src/aryx/resolution/blocking.py, tests/test_blocking.py, docs/wiki/gaps/G2.md]
---

# block-smith — Close G2 (Naive Blocking)

## Wiki Protocol
Read first: `docs/wiki/STATE.md`, `docs/wiki/sources/gap_map.md` §G2, `docs/wiki/gaps/G2.md` (create if missing).
Write last: Work Log entry on G2.md + handoff block, committed WITH the code.

## Verified Baseline (do not re-derive)
- `src/aryx/resolution/classical.py:block_key` — blocks only on `text[:4]`
- "Smith, John" and "Smithson, Alice" collide; "John Smith" and "Smith John" split
- No phonetic, no token-set fallback
- No block-size cap: a single large block becomes O(n²) comparisons

## Implementation Prompt

You are improving entity resolution blocking in a FastAPI platform. The blocking strategy in `src/aryx/resolution/classical.py` is too coarse. Three changes:

**1. Extract blocking into its own module `src/aryx/resolution/blocking.py`**

Implement a `MultiKeyBlocker` class:
- **Prefix key:** `normalize(text)[:4]` (keep existing behaviour as one key)
- **Token-set key:** sorted tuple of the first token of each word (e.g. "John Smith" → ("john", "smith"); "Smith, John" → same). Covers transpositions.
- **Soundex key:** American Soundex of the first token of the normalized text. Covers phonetic near-misses (e.g. "Schmidt" / "Schmit").
- A record can emit **multiple keys** — it appears in all matching blocks.
- **Block-size cap:** if a block exceeds `max_block_size=5000`, log a WARNING and skip the block (pathological data like blank names would create O(n²) work). Make `max_block_size` a constructor param.
- `block(records) -> dict[str, list[ResolutionRecord]]` — same signature as the current `block()` function so `run.py` can swap with a one-line change.

**2. Update `src/aryx/resolution/classical.py`**
- Keep `normalize`, `block_key`, `string_score`, `cosine`, `score_pair` unchanged.
- Remove the `block()` function (it moves to `blocking.py`).
- Add a thin `block(records, max_block_size=5000)` shim that delegates to `MultiKeyBlocker` — this keeps `run.py` imports unchanged.

**3. Update `src/aryx/resolution/run.py`**
- No changes needed if the shim is in place. Confirm imports still resolve.

**4. Tests — `tests/test_blocking.py`:**
- `MultiKeyBlocker` places transposed names in the same block (token-set key)
- `MultiKeyBlocker` places phonetic near-misses in the same block (Soundex key)
- `MultiKeyBlocker` still splits clearly different names
- Block-size cap: block with >5000 records is skipped, warning logged
- `normalize` + `block_key` unchanged (regression test)
- Golden: record "John Smith" and "Smith, John" must share at least one block key

**Constraints:**
- No new pip dependencies: Soundex must be implemented inline (it is 10 lines of pure Python — do not add `jellyfish` or `phonetics`).
- Keep every module ≤150 lines. Split `blocking.py` if needed.
- Type hints + docstrings per house style (mirror `classical.py`).
- Run `PYTHONPATH=src python -m pytest tests/test_blocking.py -v` to confirm before handoff.

## Acceptance Gates
- Full suite green including new test_blocking.py (≥5 new tests).
- `python -c "from aryx.resolution.blocking import MultiKeyBlocker; b = MultiKeyBlocker(); keys = list(b.block([]).keys()); print('ok')"` runs without error.
- Transposition test: "John Smith" and "Smith John" share a block key.

## Handoff
Write `docs/wiki/handoffs/block-smith-<date>.md` per WIKI_SCHEMA.md.
`unblocks: [G9, G10, G7, G1+G5]`
Warnings: "block-size cap default=5000 — tune after G9 measures real skew on production data"
