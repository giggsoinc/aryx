-- 0032 — Knowledge Graph Intake & Validation (C05).
-- One immutable version per validated graph. The original JSON is stored
-- verbatim; the canonical (normalized) graph is stored alongside for bounded
-- adapter reads by the graph profiler. Same content hash under a graph is
-- stored once. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_graph_version (
    id                      BIGSERIAL PRIMARY KEY,
    workspace_id            BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    graph_id                TEXT NOT NULL,
    version                 TEXT NOT NULL,
    content_hash            TEXT NOT NULL,
    dataset_ids             JSONB NOT NULL DEFAULT '[]'::jsonb,
    entity_count            BIGINT NOT NULL DEFAULT 0,
    relationship_count      BIGINT NOT NULL DEFAULT 0,
    duplicate_entities      INTEGER NOT NULL DEFAULT 0,
    duplicate_relationships INTEGER NOT NULL DEFAULT 0,
    dangling_relationships  INTEGER NOT NULL DEFAULT 0,
    schema_status           TEXT NOT NULL DEFAULT 'valid',
    normalized_graph_ref    TEXT NOT NULL DEFAULT '',
    graph_json              JSONB NOT NULL,
    normalized              JSONB NOT NULL,
    report                  JSONB NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, graph_id, version),
    UNIQUE (workspace_id, graph_id, content_hash)
);

CREATE INDEX IF NOT EXISTS aryx_graph_version_ws_idx
    ON aryx_graph_version(workspace_id, graph_id);
