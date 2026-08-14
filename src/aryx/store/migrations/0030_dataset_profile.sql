-- 0030 — Deterministic Dataset Profiler (C03).
-- One versioned profile per (dataset_id, dataset_version). The full profile
-- document is stored as JSONB; re-profiling a version replaces it in place.
-- Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_dataset_profile (
    id                 BIGSERIAL PRIMARY KEY,
    workspace_id       BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    dataset_profile_id TEXT NOT NULL,
    dataset_id         TEXT NOT NULL,
    dataset_version    TEXT NOT NULL,
    row_count          BIGINT NOT NULL DEFAULT 0,
    column_count       INTEGER NOT NULL DEFAULT 0,
    profile_status     TEXT NOT NULL DEFAULT 'valid',
    profile            JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_dataset_profile_ws_idx
    ON aryx_dataset_profile(workspace_id, dataset_id);
