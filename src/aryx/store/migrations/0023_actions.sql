-- G13 kinetic action layer v1: declared, parameterized, permissioned
-- mutations whose every execution is audited. Effects write to Postgres
-- (source of truth) first; the graph is a projection and is never mutated
-- directly. Definitions version by append (superseded_by pointer) per the
-- ontology change-log precedent (migration 0014). aryx_action_execution is
-- the kinetic provenance: effect_log records before/after per effect.

CREATE TABLE IF NOT EXISTS aryx_action (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL,
    name          TEXT NOT NULL,
    definition    JSONB NOT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    superseded_by BIGINT,
    created_by    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_name
    ON aryx_action (workspace_id, name);

CREATE TABLE IF NOT EXISTS aryx_action_execution (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL,
    action_id    BIGINT NOT NULL,
    entity_id    BIGINT NOT NULL,
    params       JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',
                 -- pending|approved|rejected|applied|failed
    requested_by TEXT,
    decided_by   TEXT,
    decided_at   TIMESTAMPTZ,
    applied_at   TIMESTAMPTZ,
    effect_log   JSONB NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_exec_pending
    ON aryx_action_execution (workspace_id, status);
