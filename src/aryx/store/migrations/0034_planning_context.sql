-- 0034 — Context and Resource Retrieval (C07).
-- One versioned planning context per (dataset_id, dataset_version). The full
-- package is stored as JSONB; re-assembling replaces it. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_planning_context (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    planning_context_id TEXT NOT NULL,
    dataset_id          TEXT NOT NULL,
    dataset_version     TEXT NOT NULL,
    context_status      TEXT NOT NULL DEFAULT 'complete',
    approved_columns    INTEGER NOT NULL DEFAULT 0,
    context             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_planning_context_ws_idx
    ON aryx_planning_context(workspace_id, dataset_id);
