-- Persistent record of every Ask question + answer + the graph calls + tokens
-- + the entity ids the answer pointed at. Powers the cross-session Ask history
-- table on the Ask page and the audit-trail downloads.

CREATE TABLE IF NOT EXISTS aryx_ask_history (
    id                BIGSERIAL PRIMARY KEY,
    workspace_id      BIGINT NOT NULL,
    asked_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    question          TEXT NOT NULL,
    answer            TEXT NOT NULL,
    tools_called      JSONB NOT NULL DEFAULT '[]',
    entity_ids        BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
    prompt_tokens     INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    latency_ms        INT NOT NULL DEFAULT 0,
    answer_model      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ask_history_ws_time
  ON aryx_ask_history (workspace_id, asked_at DESC);
