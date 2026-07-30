-- 0040 — Dashboard Composition (C14).
-- One composed dashboard model per (dataset_id, dataset_version) — re-running
-- (a new C13-approved run for the same version) replaces it in place, same
-- convention as aryx_dashboard_spec / aryx_execution_plan. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_dashboard_model (
    id                    BIGSERIAL PRIMARY KEY,
    workspace_id          BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    dashboard_model_id    TEXT NOT NULL,
    spec_id               TEXT NOT NULL,
    dataset_id            TEXT NOT NULL,
    dataset_version       TEXT NOT NULL,
    section_count         INTEGER NOT NULL DEFAULT 0,
    composition_status    TEXT NOT NULL,
    composed_by           TEXT NOT NULL DEFAULT 'deterministic',
    model                 JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_dashboard_model_ws_idx
    ON aryx_dashboard_model(workspace_id, dataset_id);
