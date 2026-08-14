-- 0042 — User Intent Capture (C01).
-- Persists every capture attempt (valid and invalid) as an auditable, versioned
-- record keyed by its correlation id. Workspace-scoped like every other table.

CREATE TABLE IF NOT EXISTS aryx_user_intent (
    id                BIGSERIAL PRIMARY KEY,
    workspace_id      BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    request_id        TEXT NOT NULL,
    schema_version    TEXT NOT NULL DEFAULT '1.0',
    uploaded_file     TEXT NOT NULL DEFAULT '',
    domain            TEXT NOT NULL DEFAULT '',
    objective         TEXT NOT NULL DEFAULT '',
    preferences       JSONB NOT NULL DEFAULT '{}'::jsonb,
    validation_status TEXT NOT NULL,
    warnings          JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors            JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, request_id)
);

CREATE INDEX IF NOT EXISTS aryx_user_intent_ws_idx
    ON aryx_user_intent(workspace_id);
