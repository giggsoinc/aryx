-- Ingestion job tracking (Increment: pipeline progress + observability).
-- Durable per-run stage progress so the UI can show which agent is working,
-- what it does, and % complete. Events form an append log of what completed.
-- Rows older than 30 days are archived then purged (see archive_old_jobs).

CREATE TABLE IF NOT EXISTS aryx_job (
    job_id         TEXT PRIMARY KEY,
    source_system  TEXT NOT NULL,
    source_dataset TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'queued',
    stage          TEXT NOT NULL DEFAULT 'queued',
    pct            INTEGER NOT NULL DEFAULT 0,
    detail         TEXT NOT NULL DEFAULT '',
    run_id         BIGINT,
    error          TEXT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS aryx_job_event (
    id      BIGSERIAL PRIMARY KEY,
    job_id  TEXT NOT NULL,
    stage   TEXT NOT NULL,
    pct     INTEGER NOT NULL DEFAULT 0,
    detail  TEXT NOT NULL DEFAULT '',
    ts      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aryx_job_archive (
    job_id         TEXT PRIMARY KEY,
    source_system  TEXT NOT NULL,
    source_dataset TEXT NOT NULL,
    status         TEXT NOT NULL,
    stage          TEXT,
    pct            INTEGER,
    detail         TEXT,
    run_id         BIGINT,
    error          TEXT,
    started_at     TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    archived_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_event_job ON aryx_job_event (job_id);
CREATE INDEX IF NOT EXISTS idx_job_finished ON aryx_job (finished_at);
