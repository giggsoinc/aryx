-- 0033 — Knowledge Graph Profiler (C06).
-- One versioned profile per (graph_id, graph_version). The full profile
-- document is stored as JSONB; re-profiling a version replaces it. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_graph_profile (
    id                 BIGSERIAL PRIMARY KEY,
    workspace_id       BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    graph_profile_id   TEXT NOT NULL,
    graph_id           TEXT NOT NULL,
    graph_version      TEXT NOT NULL,
    entity_count       BIGINT NOT NULL DEFAULT 0,
    relationship_count BIGINT NOT NULL DEFAULT 0,
    path_count         INTEGER NOT NULL DEFAULT 0,
    profile_status     TEXT NOT NULL DEFAULT 'valid',
    profile            JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, graph_id, graph_version)
);

CREATE INDEX IF NOT EXISTS aryx_graph_profile_ws_idx
    ON aryx_graph_profile(workspace_id, graph_id);
