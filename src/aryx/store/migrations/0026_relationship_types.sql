-- 0026 — Declared relationship types (Slice W2 commit 4 / option g).
-- The pipeline historically created relationship INSTANCES; modelling needs
-- a place to declare relationship TYPES (owl:ObjectProperty) so the canvas
-- can persist a drawn edge before any ingest has run.

CREATE TABLE IF NOT EXISTS aryx_relationship_type (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, source_type, name, target_type)
);

CREATE INDEX IF NOT EXISTS aryx_relationship_type_ws_idx
    ON aryx_relationship_type(workspace_id);
