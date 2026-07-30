# C01-C12 — Status & How Each Is Done

What's built for each dashboard/backend component, how it works, and what
backs it with tests. See [dashboard_components_C01-C08.md](dashboard_components_C01-C08.md)
for the UI wiring and [intent_gated_autorun.md](intent_gated_autorun.md) for
the cross-component autorun mechanism referenced throughout.

## Summary

| # | Component | Status | LLM? |
|---|---|---|---|
| C01 | User Intent Capture | Complete | No |
| C02 | Dataset Ingest | Complete | No |
| C03 | Deterministic Dataset Profile | Complete | No |
| C04 | Semantic Mapping | Complete | No (embeddings only, best-effort) |
| C05 | Knowledge Graph Intake & Validation | Complete | No |
| C06 | Knowledge Graph Profiler | Complete | No |
| C07 | Workspace Planning Context | Complete | No |
| C08 | Andie Jr Planning Orchestrator | Complete | Yes — the only one that calls an LLM |
| C09 | Pre-Execution Specification Validation | Complete | No — code-only gate on C08's output |
| C10 | Preprocessing and Transformation | Complete | No — deterministic, chained onto C09's approval |
| C11 | Execution Compiler | Complete | No — MVP policy is no LLM; binds approved params to vetted templates only |
| C12 | Deterministic Analysis Execution | Complete | No — real values only, from a fixed set of vetted templates |

All twelve are implemented and covered by tests. C09 and C10 have no UI/API
surface of their own — both are internal to C08's run flow — their output IS
surfaced inside C08's existing `DashboardSpecPanel.tsx`: an "approved" badge
(C09), a distinct rose `controlled_failure` block when both attempts are
rejected (C09), and a compact per-column transformation summary (C10) — see
their sections below. C11 has its own read-only API (`GET /execution-plan/*`)
and its own panel (`ExecutionPlanPanel.tsx`), scoped to the whole workspace
only — see its section.
The intent-gated autorun (C03-C07) is implemented but not yet manually
smoke-tested end-to-end (see [intent_gated_autorun.md](intent_gated_autorun.md#verification)).

---

## C01 — User Intent Capture

**Status:** Complete. Deterministic, no LLM.

**How it's done:** `IntentForm.tsx` posts `uploaded_file`, `domain`,
`objective`, and preferences (chart types, audience, KPIs, dimensions, date
range) to `POST /intent/capture`. [`intent/capture.py`](../src/aryx/intent/capture.py)
validates required fields (blocks on missing), normalizes text/dates/lists,
checks chart types and audience against catalogues (warns but keeps unsupported
values), and stamps a versioned `UserIntent` with a correlation `request_id`.
Every attempt — valid or invalid — is persisted via `IntentStore.save()` for
audit (`aryx_user_intent` table, migration `0028_user_intent.sql`).

**Test:** `tests/test_intent_capture.py`.

---

## C02 — Dataset Ingest

**Status:** Complete.

**How it's done:** Files land through the Onboard upload flow
(`POST /admin/ingest/file` in [`file_ingest_api.py`](../src/aryx/api/file_ingest_api.py)),
which runs as a background task. For each data file,
[`dataset/ingest.py`](../src/aryx/dataset/ingest.py)'s `register_dataset()`
stores the raw bytes as an immutable, versioned snapshot
(`aryx_dataset_version` table) keyed by `(dataset_id, version)`, deduping
identical re-uploads (`ingestion_status: accepted | duplicate`). The dashboard's
`DatasetsPanel.tsx` is a pure read view — `GET /dataset/versions` — polling
every 3s; it has no upload UI of its own (upload happens in `/start`, i.e.
Onboard).

**Test:** `tests/test_dataset_ingest.py`.

---

## C03 — Deterministic Dataset Profile

**Status:** Complete.

**How it's done:** [`profiler/profile.py`](../src/aryx/profiler/profile.py)
reads a dataset snapshot and infers, per column: data type, an analytical role
(`identifier` / `measure` / `dimension` / `time` / `status` / `attribute`), and
quality flags (nulls, cardinality, etc.) — no LLM, pure heuristics over the
actual values. `run_profile()` in `profiler/run.py` is the shared glue:
fetch snapshot → profile → persist (`ProfileStore`). It's called once per
dataset from `run_downstream()` (see the autorun doc) rather than inline
during ingest.

**Test:** `tests/test_dataset_profiler.py`.

---

## C04 — Semantic Mapping

**Status:** Complete.

**How it's done:** [`semantic/interpret.py`](../src/aryx/semantic/interpret.py)
takes the C03 profile and the workspace's ontology vocabulary
(`OntologyStore.list_types()`), builds candidate terms, and matches each
column to an ontology concept — lexically always, plus an optional embedding
similarity pass via the local broker (`ollama`) when available; falls back to
lexical-only if embeddings fail. `run_interpret()` in `semantic/run.py` also
resolves the dataset's domain (via its C01 intent, for provenance only —
never blocks) and persists a `SemanticProfile` (`SemanticStore`).

**Test:** `tests/test_semantic_interpret.py`.

---

## C05 — Knowledge Graph Intake & Validation

**Status:** Complete.

**How it's done:** [`graph_intake/build.py`](../src/aryx/graph_intake/build.py)
assembles a graph JSON from every entity/relationship landed in the
workspace (`EntityStore`), then [`validate.py`](../src/aryx/graph_intake/validate.py)
validates and normalizes it. `run_intake()` in `graph_intake/run.py` hashes
the graph content (`sha256`) and is idempotent — an unchanged graph returns
the existing version instead of creating a new one; a changed graph gets a new
immutable version (`v1`, `v2`, ...) in `GraphIntakeStore`. The UI
(`GraphIntakePanel.tsx`) also exposes a manual "Re-validate graph" button that
calls the same `run_intake()` on demand, independent of the autorun gate.

**Test:** `tests/test_graph_intake.py`.

---

## C06 — Knowledge Graph Profiler

**Status:** Complete.

**How it's done:** [`graph_profiler/profile.py`](../src/aryx/graph_profiler/profile.py)
loads the latest validated C05 graph and computes structural stats — entity
type coverage, verified traversal paths up to a max depth, whether the graph
is currently valid. `run_graph_profile()` resolves the workspace's most recent
C01 objective as a relevance hint for which paths matter (best-effort, never
blocks), then persists via `GraphProfileStore`.

**Test:** `tests/test_graph_profiler.py`.

---

## C07 — Workspace Planning Context

**Status:** Complete. Two variants exist: per-dataset and workspace-wide.

**How it's done:** [`planning/assemble.py`](../src/aryx/planning/assemble.py)
merges C03 (profile) + C04 (semantic) + C06 (graph profile) + C01 (intent) into
one `PlanningContext`, tagging `context_status` as `complete` / `incomplete` /
`blocked` based on what's missing. `run_context()` builds this per dataset;
`run_workspace_context()` builds the single merged view spanning every
dataset in the workspace, deliberately keeping columns grouped per dataset
(never flattened by name, since the same column name can mean different
things in different files). The dashboard shows the workspace-scope version
(`WorkspacePlanningContextPanel.tsx`); the per-dataset version is fetched
inline inside `DatasetsPanel.tsx`'s expandable row.

**Test:** `tests/test_planning_context.py`.

---

## C08 — Andie Jr Planning Orchestrator

**Status:** Complete. The only LLM-calling component, and strictly on-demand.

**How it's done:** [`andie_planner/generate.py`](../src/aryx/andie_planner/generate.py)
builds a prompt (`prompt.py`) from the C07 planning context and calls the
configured LLM to draft a candidate, non-executable dashboard spec — which
columns, operations, charts, and cross-dataset references would answer the
user's intent. That raw draft is never trusted directly:
[`ground.py`](../src/aryx/andie_planner/ground.py) code-verifies every
column/operation/chart/path reference against the actual approved data before
anything reaches the UI; anything unverifiable is dropped or flagged, not
silently kept. `DashboardSpecPanel.tsx` only triggers this via an explicit
button click (`runAndiePlanner` / `runAndiePlannerWorkspace`) — it never
auto-runs on ingest or on the C03-C07 autorun gate, since it's the one step
with real (non-deterministic, costly) LLM inference behind it.

**Test:** `tests/test_andie_planner.py`.

---

## C09 — Pre-Execution Specification Validation

**Status:** Complete. No LLM — a code-only gate on C08's output, internal to
its run flow (no UI panel, no public API).

**How it's done:** C08's `ground.py` philosophy is "strip unsupported parts
and keep going, recording warnings" — it always returns a spec. C09 is the
opposite: a formal reject/approve gate. [`spec_validation/checks.py`](../src/aryx/spec_validation/checks.py)
runs 10 named checks against the grounded `DashboardSpec` — several of them
*promote* a C08 grounding warning (e.g. `unapproved_column`) into a hard C09
error, which is how a column C08 already stripped (e.g. `annual_revenue`)
still surfaces as a rejection reason. [`validate.py`](../src/aryx/spec_validation/validate.py)
aggregates the 10 results into a `ValidationReport` (`approved` /
`rejected`), and on rejection builds a structured `RepairRequest` — per-error
`allowed_columns` / `allowed_operations` / `allowed_replacements` — for
exactly one correction retry.

[`spec_validation/run.py`](../src/aryx/spec_validation/run.py)'s
`run_spec_validation()` enforces the retry cap **server-side**: it counts
prior attempts persisted for a `validation_id` before running any check, and
short-circuits to a rejected report the moment the cap (2: one initial + one
retry) is hit — independent of how many times the caller calls it. This is
wired into `andie_planner/run.py`'s `run_planner()` / `run_planner_workspace()`
via `_run_c09_with_bounded_retry()`: validate → if rejected, ask the LLM for
one corrected candidate (via a new optional `repair_constraints` param on
`generate.py`'s `assemble_spec`/`assemble_workspace_spec`, additive and a
no-op by default) → validate again → approved becomes the final result,
still-rejected becomes a terminal `PlannerResult(status="controlled_failure",
error_code="planner_validation_retry_exhausted")`. `PlannerResult` gained a
`validation` field carrying the latest `ValidationReport` for audit.

**Test:** `tests/test_spec_validation.py` (17 tests — one per check, the
approved happy path, attempt/retry bookkeeping, workspace-mode column
lookup). `tests/test_andie_planner.py`'s existing 30 tests still pass
unchanged, confirming the C09 wiring is additive.

---

## C10 — Preprocessing and Transformation

**Status:** Complete. No LLM, fully deterministic. Chained onto C09's
approval inside C08's run flow — no button, no API of its own.

**How it's done:** Never mutates the C02 raw snapshot. [`preprocess/policy.py`](../src/aryx/preprocess/policy.py)'s
`referenced_columns()` scopes work to exactly the columns the **approved**
spec touches (KPI/analysis source_columns, measures, filters, group_by,
chart axes) for one dataset — never the whole dataset. `derive_conversion_policy()`
maps each of those columns straight from C03's own `canonical_type`
(numeric → `numeric_conversion`, datetime → `date_conversion`, etc.) — there
is no authoring surface; if C03 already computed the type, C10 doesn't ask
again. `derive_null_policy()` is a small fixed rule: a column feeding a
numeric aggregation (`sum`/`average`/`median`/`ratio`/`percentage`) excludes
nulls from that aggregate, everything else retains them.

[`preprocess/transform.py`](../src/aryx/preprocess/transform.py) does the
actual per-column conversion and carries the soft safety gate: if a column's
conversion failure rate exceeds `THRESHOLD` (10%, an engineering default —
not spec'd, flagged as adjustable), **that column alone** reverts to its
original values and is marked `reverted=True` — one messy column never
blocks clean ones next to it, and the dataset is marked
`status="ready_with_warnings"` instead of `"ready"` rather than being
blocked outright. In practice this path is rarely hit for numeric/date/
boolean conversions: C03 only calls a column "numeric"/"datetime" if
*every* non-null value already parses, using the same evidence-based rule
C10's own converters apply — so the gate mainly protects against a stale
profile or a parser divergence, not everyday dirty data.

[`preprocess/run.py`](../src/aryx/preprocess/run.py)'s `run_preprocess()` is
the glue: loads the raw snapshot bytes (reusing C03's own row loader),
resolves policies, converts, and persists an `AnalysisDataset` (`store/analysis_dataset_store.py`,
migration `0037_analysis_dataset.sql`). This is a **transformation log**
(counts, per-column outcomes, a `lineage_map_ref` placeholder) — not a
second materialized copy of the row data, since there's no downstream
execution/compute stage yet to consume one.

Wired into `andie_planner/run.py`'s `_run_c10_for_approved()`: right after
C09 reports `status: "approved"`, it runs C10 once per dataset the spec's
KPIs/analyses reference (handles both single-dataset and workspace-scope
specs) and appends each `AnalysisDataset` to `PlannerResult.analysis_datasets`
— best-effort, a C10 failure never downgrades the C08/C09 outcome.

**Test:** `tests/test_preprocess.py` (16 tests — column-reference scoping,
policy derivation from an explicit fake profile, per-type conversion,
threshold/revert behavior for numeric/date/boolean, and one true
end-to-end run with `DatasetStore`/`AnalysisDatasetStore` mocked).

---

## C11 — Execution Compiler

**Status:** Complete. No LLM (MVP policy), fully deterministic. Compilation
itself is chained onto C10 (no button — it's `_run_c11_for_spec()`, called
from `andie_planner/run.py` right after C10's per-dataset loop), but unlike
C09/C10 it has its own read-only API and UI panel (see below).

**How it's done:** [`execution_compiler/templates.py`](../src/aryx/execution_compiler/templates.py)
is the fixed, vetted catalogue the compiler may ever bind parameters to
(`filter_equals`, `filter_in`, `count_rows`, `{sum,average,median}_numeric`,
`safe_ratio`, and their `grouped_*` variants) — an operation with no template
here has no execution path; the compiler rejects it rather than improvising
SQL/Python. [`execution_compiler/compile.py`](../src/aryx/execution_compiler/compile.py)'s
`compile_plan_for_spec()` walks the WHOLE approved spec's KPIs and analyses —
one plan per spec, never fragmented per dataset, even when a workspace-scope
spec's KPIs span several datasets: a `count`/`sum`/`average`/`median` KPI
becomes an optional `filter_*` node feeding a `count_rows`/`*_numeric` node; a
`ratio`/`percentage` KPI compiles its numerator and denominator into their
own filter+measure nodes before a `safe_ratio` node depends on both
(`zero_denominator_policy` carried straight through — C09 already guaranteed
both operands exist); an `Analysis` (`group_by` + a `metric` pointing at a
KPI) becomes one `grouped_*` node keyed off that KPI's own operation. Node
IDs are derived deterministically from the KPI/analysis ID (e.g.
`op_kpi_renewal_rate_ratio`) — same input always compiles to the same node
graph, only `execution_plan_id` varies per run. (`compile_plan()` is the
lower-level, dataset-scoped primitive it wraps — still directly unit-tested,
just no longer called per-dataset from the glue.)

[`execution_compiler/validate.py`](../src/aryx/execution_compiler/validate.py)
is the compiler's own structural self-check — never a re-litigation of C09's
business-rule validation (numeric measures, ratio operand presence, operation
whitelisting are already guaranteed by the time a spec reaches here). It
checks every node's template is known with exactly its required parameter
keys, node IDs are unique, dependencies resolve within the plan, the
dependency graph is acyclic (Kahn's algorithm), and the plan doesn't exceed
`node_limit` (200, an engineering default — flagged as adjustable, same as
C10's `THRESHOLD`). Any structural failure marks `compilation_status:
"rejected"` — auditable, not dropped. `row_limit` is clamped to the sum of
every referenced dataset's row count (from C10's `AnalysisDataset.row_count`,
accumulated across C10's per-dataset loop) when smaller than the default cap.

[`execution_compiler/run.py`](../src/aryx/execution_compiler/run.py) →
actually inlined as `_run_c11_for_spec()` in `andie_planner/run.py` rather
than a separate glue module, since it needs the total row count C10's loop
just accumulated. Called once per spec (after C10's per-dataset loop
finishes), keyed by `spec.dataset_id` — the real dataset_id in single-dataset
mode, or `"workspace_{id}"` in workspace mode (same convention
`DashboardSpecStore` already uses). Persisted via `ExecutionPlanStore`
(`aryx_execution_plan` table, migration `0038_execution_plan.sql`), one row
per `(dataset_id, dataset_version)`, appended to
`PlannerResult.execution_plans` — best-effort, a C11 failure never
downgrades the C08/C09/C10 outcome.

**UI:** `ExecutionPlanPanel.tsx` — read-only, whole-workspace scope only:
fetches `GET /execution-plan/workspace_{id}` and shows that one plan (node
list with template/parameters/dependencies, `compilation_status`,
acyclic/row-limit/node-count summary, and any rejection issues), or a "run
the workspace-wide spec first" empty state. It does not show single-dataset
runs' plans (out of scope by design — ask if that's needed later).

**Extended for C12:** each `ExecutionNode` now also carries its own
`dataset_id` (from the originating KPI/Analysis) so a single plan can be
executed across several datasets, and `ExecutionPlan` carries three lookup
maps C12 needs to turn raw node results back into business-level ones:
`kpi_final_node` (kpi_id → the node whose result IS that KPI's value),
`kpi_lineage_nodes` (kpi_id → every node compiled for it, for
`lineage.operation_ids`), and `analysis_node` (analysis_id → its grouped
node). `grouped_safe_ratio`'s template also grew `numerator_values`/
`denominator_values`/`zero_policy` — the original design only carried
`status_column` for display, which wasn't enough to actually execute a
grouped ratio; C12 surfaced the gap.

**Test:** `tests/test_execution_compiler.py` (18 tests — count/sum/ratio KPI
compilation, grouped-analysis compilation for ratio/sum/unknown metrics,
deterministic node IDs across repeated compiles, row-limit clamping,
node-limit rejection, and each `validate.py` structural check in isolation).

---

## C12 — Deterministic Analysis Execution

**Status:** Complete. No LLM, fully deterministic. On-demand only, like
C08 — triggered explicitly (`POST /execution-run/run`), never chained onto
C08-C11's approval flow. This is the engine C11's own doc flagged as
"not-yet-built" — C11 only compiled and validated the DAG; C12 actually
runs it.

**How it's done:** [`analysis_execution/data.py`](../src/aryx/analysis_execution/data.py)'s
`load_typed_rows()` re-loads the C02 raw snapshot (C10 never materialized a
second copy of the row data — only a transformation log) and re-applies the
EXACT SAME conversion policy C10 already logged (`derive_conversion_policy` +
`convert_column`, reused directly), so C12 executes against the same typed
values C10's log describes rather than a second, possibly-divergent
conversion pass.

[`analysis_execution/execute.py`](../src/aryx/analysis_execution/execute.py)'s
`run_plan()` walks C11's compiled nodes in dependency order and dispatches
each to its template: `filter_equals`/`filter_in` produce a row-index list;
`count_rows` counts it (or all rows, if the node has no filter dependency);
`{sum,average,median}_numeric` aggregate a column over that index set,
excluding nulls; `safe_ratio` divides two upstream results, returning
`value: null` (never a fabricated 0%) when the denominator is zero;
`grouped_*` re-derive the same breakdown per distinct value of the group
column, directly against the dataset's rows. A node that fails (unknown
template, bad column) is recorded in `errors` and skipped — one bad node
degrades the run to `status: "partial"`, never crashes it. A
`maximum_runtime_seconds` wall-clock check between nodes stops execution
gracefully (remaining nodes marked failed) rather than running unbounded;
`maximum_rows` caps how many rows are loaded per dataset.

[`analysis_execution/run.py`](../src/aryx/analysis_execution/run.py)'s
`run_analysis_execution()` is the glue: fetches the latest `ExecutionPlan`
and the approved spec that produced it, loads typed rows for every dataset
the plan's nodes reference, runs the executor, then uses the plan's
`kpi_final_node`/`analysis_node` maps to turn raw node results into
`KpiResult`s (value, `display_value` formatted per the KPI's `format` —
`percentage`/`currency`/plain number — numerator/denominator for ratios,
sample size, excluded-null count, and lineage) and `AnalysisResult`s (one
row per group). Persisted via `ExecutionRunStore` (`aryx_execution_run`
table, migration `0039_execution_run.sql`) — **insert-only**, unlike
C08-C11's upsert-in-place versioning: a re-triggered run is a genuinely new,
independently timed execution, so history is kept rather than overwritten.

**UI:** `ExecutionRunPanel.tsx` — whole-workspace scope only (same
convention as C11's panel), with its own "Run analysis" button
(`POST /execution-run/run`) — nothing computes until pressed. Shows the
latest run's status, per-KPI cards (value, numerator/denominator, sample
size, excluded nulls, lineage columns), and a per-group table for each
analysis. Fetches the latest run once on load (no auto-poll — a run is an
explicit action, not a background computation to watch for).

**Test:** `tests/test_analysis_execution.py` (10 tests — exercises real
`compile_plan()` output, not mocked: the renewal-rate worked example from
this component's own spec doc (211/340 = 62.06%), sum-KPI null exclusion and
currency formatting, count KPIs, grouped ratio/sum breakdowns by region,
zero-denominator returning `null` instead of crashing, an unloaded dataset
degrading to empty rows instead of crashing, and `maximum_runtime_seconds`
stopping gracefully). The DB-backed glue (`run.py`'s `run_analysis_execution`)
needs a real Postgres connection and is not covered here — same boundary
`spec_validation/run.py` and `preprocess/run.py` already draw.

---

## Cross-cutting: what makes C03-C07 "automatic"

C03-C07 don't run the moment a file lands — they run once **both** a dataset
is ingested (C02) AND a valid C01 intent exists for the workspace. Whichever
condition completes second triggers `run_downstream()`
([src/aryx/pipeline/downstream.py](../src/aryx/pipeline/downstream.py)), the
one function shared by both the ingest path and the intent-capture path. Full
mechanism, code paths, and files touched are in
[intent_gated_autorun.md](intent_gated_autorun.md).

## What's not yet verified

- **C09 is real-tested**, not just parsed: a scratch venv with real
  `pydantic`/`psycopg` installed ran all 127 relevant tests (C09's 17 +
  every C0x test the C09 change touches or sits near) and a manual
  end-to-end run of `_run_c09_with_bounded_retry` for both outcomes — a
  rejected spec recovered by the one retry, and one still rejected after
  both attempts (`controlled_failure`). No DB was available, so
  `SpecValidationStore`'s actual Postgres round-trip is untested (mocked in
  the manual run above).
- No live end-to-end run of the intent-gate + backfill (C03-C07) or a real
  API boot — `aryx.api` eagerly imports the full app graph (FalkorDB,
  boto3, anthropic, spaCy, oracledb, ...), too heavy to install just for a
  smoke import in this environment.
- No dedicated test file yet for `pipeline/downstream.py` itself (the
  individual `run_profile`/`run_interpret`/etc. functions it calls are each
  covered by their own component's test, listed above).
