-- G10 human adjudication queue.
-- Every row — including auto_llm ones — is a labeled (pair, score, verdict)
-- training example. This table is the long-term data moat: it prices into
-- any future fine-tuned matcher. Schedule a quarterly export.

CREATE TABLE IF NOT EXISTS aryx_adjudication (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL,
    run_id          BIGINT NOT NULL,
    left_record_id  BIGINT NOT NULL,
    right_record_id BIGINT NOT NULL,
    score           REAL NOT NULL,
    llm_verdict     BOOLEAN,
    llm_reason      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|auto_llm
    decided_by      TEXT,
    decided_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_adj_pending
    ON aryx_adjudication (workspace_id, status);
