-- 0031 — Semantic Field Interpreter (C04).
-- One versioned semantic profile per (dataset_id, dataset_version). Accepted
-- annotations and unresolved fields are stored together in the JSONB document
-- but are distinct arrays inside it (persisted separately per the spec).
-- Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_semantic_profile (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    semantic_profile_id TEXT NOT NULL,
    dataset_id          TEXT NOT NULL,
    dataset_version     TEXT NOT NULL,
    domain              TEXT NOT NULL DEFAULT '',
    annotation_count    INTEGER NOT NULL DEFAULT 0,
    unresolved_count    INTEGER NOT NULL DEFAULT 0,
    profile_status      TEXT NOT NULL DEFAULT 'valid',
    profile             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_semantic_profile_ws_idx
    ON aryx_semantic_profile(workspace_id, dataset_id);
