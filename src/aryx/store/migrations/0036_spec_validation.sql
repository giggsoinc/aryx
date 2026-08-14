-- 0036 — Pre-Execution Specification Validation (C09).
-- One row per validation attempt, keyed by (workspace_id, validation_id, attempt).
-- Persisted even on rejection — the persisted attempt COUNT is what enforces
-- the single-retry cap server-side, independent of caller behavior.

CREATE TABLE IF NOT EXISTS aryx_spec_validation (
    id               BIGSERIAL PRIMARY KEY,
    workspace_id     BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    validation_id    TEXT NOT NULL,
    attempt          INTEGER NOT NULL,
    spec_id          TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL,
    report           JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, validation_id, attempt)
);

CREATE INDEX IF NOT EXISTS aryx_spec_validation_ws_idx
    ON aryx_spec_validation(workspace_id, validation_id);
