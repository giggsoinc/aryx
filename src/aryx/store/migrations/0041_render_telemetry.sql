-- 0041 — Frontend Dashboard Renderer (C15) telemetry.
-- Insert-only, like aryx_execution_run — each render is a distinct, timed
-- event, not a versioned artifact to upsert in place. Workspace-scoped.

CREATE TABLE IF NOT EXISTS aryx_render_telemetry (
    id                          BIGSERIAL PRIMARY KEY,
    workspace_id                BIGINT NOT NULL REFERENCES aryx_workspace(id) ON DELETE CASCADE,
    render_id                   TEXT NOT NULL,
    dashboard_model_id          TEXT NOT NULL,
    render_status               TEXT NOT NULL,
    rendered_component_count    INTEGER NOT NULL DEFAULT 0,
    warning_count               INTEGER NOT NULL DEFAULT 0,
    unsupported_component_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    accessibility_checks        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, render_id)
);

CREATE INDEX IF NOT EXISTS aryx_render_telemetry_ws_idx
    ON aryx_render_telemetry(workspace_id, dashboard_model_id, created_at DESC);
