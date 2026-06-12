-- G1+G5: chunked block-wise resolution + stage-level checkpoints.
-- Block membership and match edges persist in Postgres so a crashed
-- resolution resumes from the first unscored block instead of restarting.
-- aryx_run_stage gives every pipeline run a durable per-stage status row.

CREATE TABLE IF NOT EXISTS aryx_block_member (
    run_id     BIGINT NOT NULL,
    block_key  TEXT NOT NULL,
    record_id  BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_block_member_key
    ON aryx_block_member (run_id, block_key);

CREATE TABLE IF NOT EXISTS aryx_block_done (
    run_id    BIGINT NOT NULL,
    block_key TEXT NOT NULL,
    PRIMARY KEY (run_id, block_key)
);

CREATE TABLE IF NOT EXISTS aryx_match_edge (
    run_id    BIGINT NOT NULL,
    left_id   BIGINT NOT NULL,
    right_id  BIGINT NOT NULL,
    score     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_match_edge_run
    ON aryx_match_edge (run_id);

CREATE TABLE IF NOT EXISTS aryx_run_stage (
    run_id      BIGINT NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',  -- running|done|failed
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    detail      JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, stage)
);
