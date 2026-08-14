# Intent-Gated Autorun for C02-C07

Status: **Implemented.** Backend gating + frontend live-refresh are both in
place; not yet manually smoke-tested end-to-end (see Verification below).

## What changed

Previously, C03-C07 (dataset profiling, semantic mapping, graph intake,
graph profiling, planning context) auto-ran on every ingest, unconditionally,
regardless of whether the user had ever filled out the intent form (C01).

Now they only run once **both** are true for a workspace:
1. At least one dataset has been ingested (C02).
2. A valid C01 intent capture exists.

Whichever of the two happens second is what triggers the run — there's no
polling loop waiting on both; each side checks the other synchronously at the
moment it completes.

## How it's done

### 1. The gate check

[`src/aryx/store/intent_store.py`](../src/aryx/store/intent_store.py) —
`IntentStore.has_valid_intent()` runs
[`select_intent_valid_exists.sql`](../src/aryx/queries/select_intent_valid_exists.sql):

```sql
SELECT EXISTS(
    SELECT 1 FROM aryx_user_intent
    WHERE workspace_id = %s AND validation_status = 'valid'
)
```

### 2. The shared downstream pipeline

[`src/aryx/pipeline/downstream.py`](../src/aryx/pipeline/downstream.py) is new.
It exposes:

- `intent_ready(dsn, workspace_id) -> bool` — thin wrapper over the store check above.
- `run_downstream(dsn, workspace_id, dataset_ids, broker=None)` — for each
  dataset id: runs C03 (`run_profile`) then C04 (`run_interpret`); then once
  for the workspace: C05 (`run_intake`), C06 (`run_graph_profile`); then for
  each dataset id again: C07 per-dataset (`run_context`); then once: C07
  workspace-scope (`run_workspace_context`). Every step is wrapped in its own
  try/except — one failure never blocks the rest, matching the pre-existing
  ingest discipline.

Both call sites below import from this one module so the C03-C07 logic exists
in exactly one place.

### 3. Trigger from the ingest side

[`src/aryx/api/file_ingest_api.py`](../src/aryx/api/file_ingest_api.py):
- `_snapshot_dataset` was trimmed to do **only** C02 (register the immutable
  snapshot). It used to also call `run_profile`/`run_interpret` inline — those
  calls were removed from here.
- At the end of `_run_files`, after every file in the batch has landed:
  ```python
  if snapshotted_ids:
      if intent_ready(settings.rdb_dsn, workspace_id):
          run_downstream(settings.rdb_dsn, workspace_id, snapshotted_ids, broker=broker)
      else:
          logger.info("intent not yet captured ws=%s; deferring C03-C07 for %d dataset(s)", ...)
  ```
  If intent isn't valid yet, C03-C07 are simply skipped for now — the datasets
  sit ingested-but-unprofiled until intent lands.

### 4. Trigger from the intent side (the backfill)

[`src/aryx/api/intent_api.py`](../src/aryx/api/intent_api.py) — `POST
/intent/capture` now takes a `BackgroundTasks` param. After saving the
capture, if `validation_status == "valid"`, it looks up every dataset id
already ingested in the workspace (`DatasetStore.list_versions`) and schedules
`run_downstream` for all of them as a background task. This is what makes
"upload files first, fill in intent later" also end up fully computed —
without it, datasets ingested before intent existed would stay unprofiled
forever.

### 5. Frontend live-refresh

The compute now happens asynchronously in the background on either trigger,
so the three panels that used to fetch once (or wait for a manual button)
were switched to polling, so results show up without user action:

- [`DatasetsPanel.tsx`](../apps/web/components/dataset/DatasetsPanel.tsx) —
  the dataset list already polled every 3s; added `loadDetail()` refresh logic
  so the currently-expanded row's profile/semantic/context are retried on each
  poll tick while still unresolved (`undefined`/`"loading"`/`"none"`), instead
  of being fetched once on first expand and never again.
- [`GraphIntakePanel.tsx`](../apps/web/components/graph/GraphIntakePanel.tsx) —
  changed from fetch-once-on-mount to a 4s poll.
- [`WorkspacePlanningContextPanel.tsx`](../apps/web/components/planning/WorkspacePlanningContextPanel.tsx) —
  same, 4s poll; also reworded the empty-state message from "click Refresh" to
  note it appears automatically once ingest + intent are both done.

Manual buttons (`Re-validate graph`, `Refresh`) are untouched — they remain as
an explicit override a user can still click at any time, independent of the
intent gate.

## Files touched

| File | Change |
|---|---|
| `src/aryx/queries/select_intent_valid_exists.sql` | new |
| `src/aryx/store/intent_store.py` | added `has_valid_intent()` |
| `src/aryx/pipeline/downstream.py` | new — `intent_ready()`, `run_downstream()` |
| `src/aryx/api/file_ingest_api.py` | `_snapshot_dataset` trimmed to C02 only; gated call to `run_downstream` at end of `_run_files` |
| `src/aryx/api/intent_api.py` | `capture` triggers backfill via `BackgroundTasks` when intent turns valid |
| `apps/web/components/dataset/DatasetsPanel.tsx` | live-refresh for open row's C03/C04/C07 detail |
| `apps/web/components/graph/GraphIntakePanel.tsx` | mount-only fetch → 4s poll |
| `apps/web/components/planning/WorkspacePlanningContextPanel.tsx` | mount-only fetch → 4s poll; copy update |
| `docs/dashboard_components_C01-C08.md` | updated to describe the gate + polling |

## Verification

- `tsc --noEmit` passes clean on `apps/web`.
- All touched Python files parse clean (`ast.parse`) — no local `venv` with
  `fastapi`/`psycopg` installed in this environment, so no live import or
  integration test was run.

## Not yet done

- No manual/integration smoke test of the actual flow (upload with no intent
  → confirm deferral log → submit intent → confirm panels populate without
  a page refresh). Recommended before calling this closed.
- Manual re-validate/refresh buttons still ignore the intent gate by design
  (explicit override) — confirm that's the intended behavior for demo/QA.
