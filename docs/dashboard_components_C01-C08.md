# Dashboard Components C01–C08

How the eight components on `/dashboard` fit together, what each one owns, and where
the code lives. Wiring is in [apps/web/app/dashboard/page.tsx](../apps/web/app/dashboard/page.tsx) —
components render top to bottom in the same order data becomes available.

## Flow at a glance

```
C01 Intent Capture
      |
C02 Dataset Ingest ── C03 Deterministic Profile ── C04 Semantic Mapping
      |
C05 Graph Intake & Validation ── C06 Graph Profile
      |
C07 Workspace Planning Context (merges C03/C04/C06 across every dataset)
      |
C08 Andie Jr Planning Orchestrator (LLM, on-demand, code-verified)
```

Each stage only reads what the stage(s) before it produced. Nothing downstream of
C07 runs automatically — C08 is explicitly on-demand because it's the only
component that calls a real LLM.

**Autorun gate.** C03-C07 (profile, semantic mapping, graph intake/validation,
graph profile, planning context) only compute once BOTH conditions hold for the
workspace: at least one dataset has been ingested (C02) AND a valid C01 intent
capture exists. Whichever condition lands second triggers the run:
- Ingest lands first → `file_ingest_api._run_files` checks `intent_ready()`; if
  intent is already valid, it runs C03-C07 immediately via `run_downstream()`.
  If not, it defers and logs a "deferring C03-C07" message.
- Intent lands first (or was missing) → `intent_api.capture` checks whether the
  submitted intent is valid; if so, it backfills C03-C07 for every dataset
  already sitting in the workspace via the same `run_downstream()`.

Shared logic lives in [src/aryx/pipeline/downstream.py](../src/aryx/pipeline/downstream.py)
(`intent_ready()`, `run_downstream()`), gated by `IntentStore.has_valid_intent()`
in [src/aryx/store/intent_store.py](../src/aryx/store/intent_store.py). The
dashboard panels for C02/C05/C07 poll every 3-4s (`DatasetsPanel`,
`GraphIntakePanel`, `WorkspacePlanningContextPanel`) so results appear as soon
as the backend finishes, without a manual refresh click.

## Component detail

### C01 — User Intent Capture
- **UI:** [IntentForm.tsx](../apps/web/components/intent/IntentForm.tsx)
- **API:** `intent_api.py` → `POST` via `api.listIntents` / intent create in `lib/api.ts`
- **Backend:** [src/aryx/intent/capture.py](../src/aryx/intent/capture.py), `catalogues.py`, `models.py`
- **Storage:** `insert_user_intent.sql`, `list_user_intents.sql`
- Captures uploaded file, domain, chart-type hint, and target audience. This is
  the only user-authored input; everything else is derived or code-computed.

### C02 — Dataset Ingest (read-only view)
- **UI:** top-level rows in [DatasetsPanel.tsx](../apps/web/components/dataset/DatasetsPanel.tsx)
- **API:** `dataset_api.py`, `listDatasetVersions` in `lib/api.ts`
- **Backend:** [src/aryx/dataset/ingest.py](../src/aryx/dataset/ingest.py), `formats.py`
- **Storage:** `insert_dataset_version.sql`, `list_dataset_versions.sql`, `select_dataset_latest*.sql`
- Shows datasets already ingested via Onboard. No ingestion logic lives here —
  purely a read/list view with a link out to each dataset's detail.

### C03 — Deterministic Dataset Profile
- **UI:** expandable row detail inside `DatasetsPanel.tsx`
- **API:** `getProfile` in `lib/api.ts` (marked `// Deterministic Dataset Profiler (C03)`)
- **Backend:** [src/aryx/profiler/profile.py](../src/aryx/profiler/profile.py), `run.py`, `models.py`
- **Storage:** `list_dataset_profiles.sql`, `select_dataset_profile*.sql`
- Column types and analytical roles (`identifier`, `measure`, `dimension`,
  `time`, `status`, `attribute`) — computed deterministically, no LLM involved.

### C04 — Semantic Mapping
- **UI:** same expandable row, next section down in `DatasetsPanel.tsx`
- **API:** semantic profile fetch alongside `getProfile` in `lib/api.ts`
- **Backend:** semantic profiling layer over `src/aryx/profiler/`
- **Storage:** `list_semantic_profiles.sql`
- Adds a semantic layer on top of the raw column profile — e.g. mapping a
  column to a business concept, not just a data type.

### C05 — Knowledge Graph Intake & Validation
- **UI:** [GraphIntakePanel.tsx](../apps/web/components/graph/GraphIntakePanel.tsx)
- **API:** `runGraphIntake`, `listGraphVersions` in `lib/api.ts`
- **Backend:** [src/aryx/graph_intake/build.py](../src/aryx/graph_intake/build.py), `validate.py`, `run.py`
- **Storage:** `insert_graph_version.sql`, `list_graph_versions.sql`, `count_graph_versions.sql`
- Read-only view of validated, versioned graph snapshots auto-derived from the
  workspace's Aryx graph. One manual action: re-validate.

### C06 — Knowledge Graph Profiler
- **UI:** same panel as C05, profile section
- **API:** `getGraphProfile` in `lib/api.ts`
- **Backend:** [src/aryx/graph_profiler/profile.py](../src/aryx/graph_profiler/profile.py), `run.py`
- **Storage:** `list_graph_profiles.sql`
- Structural profile of the validated graph (entity/edge shape, coverage) shown
  next to the intake results.

### C07 — Workspace Planning Context (workspace scope)
- **UI:** [WorkspacePlanningContextPanel.tsx](../apps/web/components/planning/WorkspacePlanningContextPanel.tsx)
- **API:** `getWorkspacePlanningContext`, `runWorkspacePlanningContext` in `lib/api.ts`
- **Backend:** [src/aryx/planning/assemble.py](../src/aryx/planning/assemble.py), `catalogues.py`, `run.py`
- **Storage:** `list_planning_contexts.sql`
- Merges C03/C04 (per-dataset profiles) and C06 (graph profile) across
  **every** dataset in the workspace. Deliberately grouped per-dataset, never
  flattened by column name — the same column name (e.g. `model`) can mean
  different things in different source files, so a name-based merge would be
  ambiguous. Status badges: `complete` / `incomplete` / `blocked`.

### C08 — Andie Jr Planning Orchestrator
- **UI:** [DashboardSpecPanel.tsx](../apps/web/components/planner/DashboardSpecPanel.tsx)
- **API:** `runAndiePlanner`, `runAndiePlannerWorkspace` in `lib/api.ts` → `andie_planner_api.py`
- **Backend:** [src/aryx/andie_planner/generate.py](../src/aryx/andie_planner/generate.py) (LLM call),
  [ground.py](../src/aryx/andie_planner/ground.py) (verification), `prompt.py`, `schema.py`, `run.py`
- **Storage:** `list_dashboard_specs.sql`, `select_dashboard_spec_latest.sql`
- The only component that calls a real LLM, and only on-demand — it never
  auto-runs on ingest. Andie drafts a candidate, non-executable dashboard spec
  from the C07 planning context; `ground.py` then code-verifies every
  column reference, operation, chart type, and cross-reference against the
  actual data before anything is displayed. The model's raw output is never
  trusted or shown directly — only the grounded, verified spec reaches the UI.

## Design invariants worth knowing

1. **One-way data flow.** No component reads from a component below it in the
   page order.
2. **Determinism before LLM.** Everything through C07 is deterministic
   (parsing, type inference, rule-based role/semantic tagging, graph
   validation). C08 is the sole non-deterministic step, isolated on purpose.
3. **Grounding, not trust.** C08's LLM output is treated as a draft only;
   `ground.py` is the gate between "the model said X" and "X is shown to the
   user."
4. **No silent auto-run for LLM work.** C02-C07 auto-run once ingest AND intent
   are both satisfied (see Autorun gate above); C08 additionally requires an
   explicit user action every time, regardless of intent/ingest state.
