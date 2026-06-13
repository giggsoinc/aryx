-- 0025 — HITL ingest questions queue (Slice 3).
-- During ingest, the pipeline may surface clarifying questions (entity
-- collapse candidates, ambiguous types, FK match disambiguation). Agents
-- read pending rows over MCP, route them to the user, write answers back.

CREATE TABLE IF NOT EXISTS aryx_ingest_question (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    job_id          TEXT NOT NULL DEFAULT '',
    kind            TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    options_json    JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggested       TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    answer          TEXT NOT NULL DEFAULT '',
    answered_by     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    answered_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS aryx_ingest_question_ws_status_idx
    ON aryx_ingest_question(workspace_id, status, created_at);
CREATE INDEX IF NOT EXISTS aryx_ingest_question_job_idx
    ON aryx_ingest_question(job_id);
