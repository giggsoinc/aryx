-- Every ontology mutation (type add/rename/disable, attribute change,
-- relationship type change, rule add/toggle) writes one row here. Powers
-- the change history view + rolls up into ontology_version snapshots.

CREATE TABLE IF NOT EXISTS aryx_ontology_change_log (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL,
    actor         TEXT NOT NULL DEFAULT '',
    op            TEXT NOT NULL,
    target_kind   TEXT NOT NULL,
    target_name   TEXT NOT NULL,
    before_json   JSONB,
    after_json    JSONB,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_change_log_ws_time
  ON aryx_ontology_change_log (workspace_id, changed_at DESC);
