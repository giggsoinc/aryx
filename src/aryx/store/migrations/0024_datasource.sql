-- 0024 — Datasource registry with Fernet-encrypted secrets (Slice 2).

CREATE TABLE IF NOT EXISTS aryx_datasource (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    config_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    secret_cipher   TEXT NOT NULL DEFAULT '',
    secret_mask     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, name)
);

CREATE INDEX IF NOT EXISTS aryx_datasource_ws_idx
    ON aryx_datasource(workspace_id);

CREATE TABLE IF NOT EXISTS aryx_secret_audit (
    id              BIGSERIAL PRIMARY KEY,
    datasource_id   BIGINT NOT NULL REFERENCES aryx_datasource(id) ON DELETE CASCADE,
    action          TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'system',
    at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
