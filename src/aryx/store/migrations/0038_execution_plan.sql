-- 0038 — Execution Compiler (C11).
-- One compiled execution plan per (dataset_id, dataset_version) — re-running
-- (a new C08 spec approval for the same dataset version) replaces it in
-- place, same convention as aryx_dashboard_spec. The full ExecutionPlan
-- (nodes, issues, or a rejected compilation) is stored as JSONB so a
-- rejected compile is auditable, not just a successful one. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_execution_plan (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    execution_plan_id   TEXT NOT NULL,
    spec_id             TEXT NOT NULL,
    dataset_id          TEXT NOT NULL,
    dataset_version     TEXT NOT NULL,
    node_count          INTEGER NOT NULL DEFAULT 0,
    compilation_status  TEXT NOT NULL,
    plan                JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_execution_plan_ws_idx
    ON aryx_execution_plan(workspace_id, dataset_id);
