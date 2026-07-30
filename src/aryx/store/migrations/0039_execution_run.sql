-- 0039 — Deterministic Analysis Execution (C12).
-- One execution run per trigger — unlike C08-C11 (upsert-in-place per
-- version), a run is insert-only: re-triggering the same plan is a genuinely
-- new, independently timed execution (fresh runtime_ms, and results can
-- legitimately differ if the underlying data changed), so history is kept
-- rather than overwritten. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_execution_run (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    execution_run_id    TEXT NOT NULL,
    execution_plan_id   TEXT NOT NULL,
    spec_id             TEXT NOT NULL,
    dataset_id          TEXT NOT NULL,
    dataset_version     TEXT NOT NULL,
    status              TEXT NOT NULL,
    kpi_count           INTEGER NOT NULL DEFAULT 0,
    analysis_count      INTEGER NOT NULL DEFAULT 0,
    run                 JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, execution_run_id)
);

CREATE INDEX IF NOT EXISTS aryx_execution_run_ws_idx
    ON aryx_execution_run(workspace_id, dataset_id, created_at DESC);
