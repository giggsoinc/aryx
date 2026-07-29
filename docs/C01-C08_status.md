# C01-C10 — Status & How Each Is Done

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

All ten are implemented and covered by tests. C09 and C10 have no UI/API
surface of their own — both are internal to C08's run flow — but their
output IS surfaced inside C08's existing `DashboardSpecPanel.tsx`: an
"approved" badge (C09), a distinct rose `controlled_failure` block when both
attempts are rejected (C09), and a compact per-column transformation summary
(C10) — see their sections below.
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
