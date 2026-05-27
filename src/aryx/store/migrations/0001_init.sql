-- Aryx landing schema (Increment 2).
-- RDB is the source of truth; the graph is a rebuildable projection.
-- Every landed record carries full provenance (system + dataset + id + run).
-- DDL is idempotent so the worker can apply it safely on every startup.

CREATE TABLE IF NOT EXISTS aryx_run (
    run_id         BIGSERIAL PRIMARY KEY,
    source_system  TEXT NOT NULL,
    source_dataset TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'running',
    record_count   INTEGER NOT NULL DEFAULT 0,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS aryx_landed_record (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT NOT NULL REFERENCES aryx_run (run_id),
    source_system    TEXT NOT NULL,
    source_dataset   TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    payload          JSONB NOT NULL,
    cleaned_at       TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_landed_run
    ON aryx_landed_record (run_id);

CREATE INDEX IF NOT EXISTS idx_landed_provenance
    ON aryx_landed_record (source_system, source_dataset, source_record_id);

CREATE TABLE IF NOT EXISTS aryx_field_profile (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES aryx_run (run_id),
    field           TEXT NOT NULL,
    non_null        INTEGER NOT NULL,
    distinct_count  INTEGER NOT NULL,
    distinct_capped BOOLEAN NOT NULL DEFAULT FALSE,
    samples         JSONB NOT NULL
);
