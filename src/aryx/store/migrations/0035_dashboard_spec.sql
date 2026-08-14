-- 0035 — Andie Jr Planning Orchestrator (C08).
-- One dashboard-spec attempt per (dataset_id, dataset_version) — re-running
-- replaces it. The full PlannerResult (spec, or controlled_error details) is
-- stored as JSONB so a failed attempt is auditable, not just a valid one.
-- Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_dashboard_spec (
    id               BIGSERIAL PRIMARY KEY,
    workspace_id     BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    spec_id          TEXT NOT NULL,
    dataset_id       TEXT NOT NULL,
    dataset_version  TEXT NOT NULL,
    status           TEXT NOT NULL,
    error_code       TEXT NOT NULL DEFAULT '',
    kpi_count        INTEGER NOT NULL DEFAULT 0,
    warning_count    INTEGER NOT NULL DEFAULT 0,
    result           JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_dashboard_spec_ws_idx
    ON aryx_dashboard_spec(workspace_id, dataset_id);
