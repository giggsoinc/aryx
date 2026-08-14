# Fix chart-type / column-fit in ask-to-visualize

## Context

Ask-to-visualize (dashboard "add a chart" flow) sometimes produces the wrong
chart type or picks the wrong column. Root-caused this session (Kaizen/Andie,
confirmed by reading the actual code — not guessed):

1. **Material gap**: the LLM drafting a chart never sees column cardinality
   or analytical role — `ApprovedColumn` (sent to the prompt) only carries
   `name`/`type`/`sample_values`. The data it needs already exists one layer
   up (`ColumnProfile.unique_count` / `candidate_role`, computed by C03's
   profiler) — it's just discarded before reaching the LLM.
2. **Method gap**: grounding (`_ground_visualization` in `ground.py`) only
   checks that a chosen `chart_type` exists in the approved list — it never
   checks whether that chart type actually *fits* the shape of the column
   it's plotting. A schema-valid-but-poor-fit choice always passes.

Both gaps are on the same code path used by full-plan generation too
(`ground_spec`), so this fix improves both ask-to-visualize and the initial
planner — but the visible symptom (from the user) is specifically wrong
chart-type/column choices in ask-to-visualize.

## Approach

Thread the already-computed profiler signal one hop further downstream, and
add one new deterministic fitness check that reuses the existing
warning/repair-retry machinery — no new retry/repair infrastructure needed.

### 1. Carry role + cardinality on `ApprovedColumn`

- `src/aryx/planning/models.py`: add `cardinality: int = 0` and
  `role: str = ""` to `ApprovedColumn` (currently `name`/`type`/`sample_values`
  only, lines 17-30).
- `src/aryx/planning/assemble.py`, `_extract_approved_columns()` (lines 44-70):
  at the construction call (lines 60-61), pass `cardinality=col.unique_count`
  and `role=role` — `role` is **already computed at line 55** for filtering
  and currently thrown away; this is a pure plumbing fix, not new logic.
  Both the single-dataset and workspace paths call this one helper, so both
  scopes get the fix from this single change.
  - Bonus cleanup (optional, do only if trivial): `_role_of` (lines 336-341)
    re-derives role from raw columns for a budget-trim sort — can be
    simplified to read `col.role` directly once available. Skip if risky.

### 2. Surface the new fields to the LLM prompt

- `src/aryx/andie_planner/delta.py`, the two `approved_columns` dict
  comprehensions (workspace mode ~186-192, single-dataset ~196-199): add
  `"cardinality": c.cardinality, "role": c.role` to each dict.
- `src/aryx/andie_planner/prompt.py`, `build_delta_prompt()`: add one short
  rule to the system/user prompt text near the existing chart-type guidance,
  e.g. "prefer `table` over `bar`/`donut`/`grouped_bar` when the grouping
  column's cardinality is high; only use time-series chart types (`line`,
  `area`, `step`, `calendar_heatmap`) when the axis column's role is `time`."
  Keep this additive — don't rewrite the existing chart-type guide.
- (Same dict-shape change applies to `generate.py`'s equivalent
  `approved_columns` payload for full-plan generation, for consistency — do
  this only if it's a same-shaped one-line change; otherwise leave for a
  follow-up so this PR stays scoped to ask-to-visualize.)

### 3. Add a chart-fitness check to grounding

- `src/aryx/andie_planner/ground.py`, `_resolve_grounding_scope()`
  (lines 253-270): alongside the existing `approved_cols: set[str]`, also
  return a `column_meta: dict[str, dict]` (name -> its full approved-column
  dict, which will now include `cardinality`/`role` once #1/#2 land). Minimal
  change: build it the same way `approved_cols` is built, just keep the dict
  instead of only the name.
- `_ground_visualization()` (lines 205-250): after the existing `x_axis`
  approval check (~line 228), add one new check: if `x_axis` resolved and
  `column_meta.get(x_axis)` exists, look up its `role`/`cardinality` and
  reject on two known-bad patterns (append
  `SpecWarning(code="chart_type_mismatch", column=x_axis, detail=...)`,
  return `None` like the existing checks):
  - Chart type in a small "low-cardinality-oriented" set (`bar`, `donut`,
    `grouped_bar`, `waterfall`) AND cardinality above a threshold (start at
    30 — same order of magnitude as profiler's own `_CATEGORICAL_MAX = 50`;
    exact value is a judgment call to validate against real data, per the
    Kaizen session's flagged risk).
  - Chart type in a "time-series" set (`line`, `area`, `step`,
    `calendar_heatmap`) AND the column's role is not `time`.
  - **Scope limit** (call out explicitly, don't try to solve now): this only
    covers charts with an explicit `x_axis`. Charts that infer their grouping
    solely from the referenced analysis's `group_by` (no `x_axis` set) are
    not covered by this first pass — flag as follow-up, don't block this fix
    on it.
- Update both call sites (`ground_spec` line 355, `ground_delta` line 602)
  to pass `column_meta` through — same pattern as the existing
  `approved_cols`/`cols_by_dataset` threading, no structural change to the
  call shape otherwise.
- **No changes needed** to the repair-retry path: `_validate_delta_draft` in
  delta.py (lines 273-277) already generically renders *any* `SpecWarning`
  into a `- [code] detail` retry hint via `append_repair_constraints` — a
  new `chart_type_mismatch` code is automatically retried the same way
  `unsupported_chart_type` already is today.

## Files touched

- `src/aryx/planning/models.py` — `ApprovedColumn` (+2 fields)
- `src/aryx/planning/assemble.py` — `_extract_approved_columns` (thread role/cardinality through)
- `src/aryx/andie_planner/delta.py` — 2 dict comprehensions (+2 keys each)
- `src/aryx/andie_planner/prompt.py` — `build_delta_prompt` (prompt text addition)
- `src/aryx/andie_planner/ground.py` — `_resolve_grounding_scope`, `_ground_visualization`, both call sites

## Verification

1. **Unit test** (new or extend existing `tests/test_andie_planner_run.py` /
   an existing ground.py test file): synthetic `ApprovedColumn`-shaped dict
   with `cardinality=500, role="dimension"` → assert a drafted `bar` chart on
   that column produces a `chart_type_mismatch` warning and `new_visualization
   is None`, and that a `table` chart on the same column passes.
2. **Unit test**: synthetic column with `role="dimension"` (not `time`) →
   assert a drafted `line` chart is rejected; a `line` chart on a
   `role="time"` column passes.
3. **Regression**: run the full existing test suite (`pytest tests/ -k
   "planner or ground or delta"` at minimum) to confirm no existing
   valid specs/deltas now get rejected — this check must not fire on
   any currently-passing case.
4. **Manual, in the running dashboard** (the merged `release/v1.5.2-dashboard`
   worktree stack already up on :8088/:3000): ask to visualize something
   that previously produced a wrong chart type/column, confirm before/after.
