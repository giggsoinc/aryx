-- 0037 — Preprocessing and Transformation (C10).
-- Metadata-only: the transformation log, quality summary, and lineage
-- reference for an analysis-ready view — NOT a materialized copy of the
-- transformed row data (no downstream execution/compute stage consumes that
-- yet; see docs/C01-C08_status.md's C10 section for the scope decision).
-- One row per (dataset_id, dataset_version); re-running replaces it in place.

CREATE TABLE IF NOT EXISTS aryx_analysis_dataset (
    id                      BIGSERIAL PRIMARY KEY,
    workspace_id            BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    analysis_dataset_id     TEXT NOT NULL,
    source_dataset_id       TEXT NOT NULL,
    source_dataset_version  TEXT NOT NULL,
    status                  TEXT NOT NULL,
    row_count               INTEGER NOT NULL DEFAULT 0,
    result                  JSONB NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, source_dataset_id, source_dataset_version)
);

CREATE INDEX IF NOT EXISTS aryx_analysis_dataset_ws_idx
    ON aryx_analysis_dataset(workspace_id, source_dataset_id);
