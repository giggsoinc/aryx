-- 0043 — Dataset Upload & Ingestion (C02).
-- A logical dataset (aryx_dataset) owns one or more immutable versions
-- (aryx_dataset_version). The raw bytes of each version live on disk
-- (aryx.store.blob_store), addressed by content_hash — never in Postgres —
-- so accepted uploads (up to 20MB each) don't bloat the RDB, stall backups,
-- or slow autovacuum. Postgres keeps the hash + row_count/columns/etc.
-- metadata only; raw_snapshot_ref is the blob store key. The same content
-- hash under a dataset is never stored twice. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_dataset (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    dataset_id    TEXT NOT NULL,
    request_id    TEXT NOT NULL DEFAULT '',
    file_name     TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id)
);

CREATE TABLE IF NOT EXISTS aryx_dataset_version (
    id                 BIGSERIAL PRIMARY KEY,
    workspace_id       BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    dataset_id         TEXT NOT NULL,
    version            TEXT NOT NULL,
    request_id         TEXT NOT NULL DEFAULT '',
    format             TEXT NOT NULL DEFAULT '',
    content_hash       TEXT NOT NULL,
    raw_snapshot_ref   TEXT NOT NULL DEFAULT '',
    row_count_estimate BIGINT NOT NULL DEFAULT 0,
    columns            JSONB NOT NULL DEFAULT '[]'::jsonb,
    sheets             JSONB NOT NULL DEFAULT '[]'::jsonb,
    ingestion_status   TEXT NOT NULL DEFAULT 'accepted',
    processing_status  TEXT NOT NULL DEFAULT 'pending',
    errors             JSONB NOT NULL DEFAULT '[]'::jsonb,
    file_name          TEXT NOT NULL DEFAULT '',
    file_size_bytes    BIGINT NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, dataset_id, version),
    UNIQUE (workspace_id, dataset_id, content_hash)
);

CREATE INDEX IF NOT EXISTS aryx_dataset_ws_idx
    ON aryx_dataset(workspace_id);
CREATE INDEX IF NOT EXISTS aryx_dataset_version_ws_idx
    ON aryx_dataset_version(workspace_id, dataset_id);
