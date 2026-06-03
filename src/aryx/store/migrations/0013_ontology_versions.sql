-- Snapshot of the workspace ontology at a point in time. Created when a
-- proposed type is approved or a rule is added/edited. Each snapshot stores
-- the full types_json + rules_json so revert and diff are cheap reads.

CREATE TABLE IF NOT EXISTS aryx_ontology_version (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL,
    version_no    INT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    types_json    JSONB NOT NULL,
    rules_json    JSONB NOT NULL DEFAULT '[]',
    created_by    TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_version_ws
  ON aryx_ontology_version (workspace_id, version_no DESC);
