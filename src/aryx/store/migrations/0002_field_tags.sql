-- Aryx field tags (Increment 4). Cheap-tier semantic types per field per run.
-- Additive migration; never edit 0001.

CREATE TABLE IF NOT EXISTS aryx_field_tag (
    id            BIGSERIAL PRIMARY KEY,
    run_id        BIGINT NOT NULL REFERENCES aryx_run (run_id),
    field         TEXT NOT NULL,
    semantic_type TEXT NOT NULL,
    is_pii        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_tag_run ON aryx_field_tag (run_id);
