-- Inference rules: when a Customer entity has revenue > $1M, classify as
-- Platinum. Evaluator reads rows from here, applies them over the entity
-- store, and writes INF_-prefixed edges + labels back into FalkorDB.

CREATE TABLE IF NOT EXISTS aryx_ontology_rule (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL,
    name          TEXT NOT NULL,
    when_clause   JSONB NOT NULL,
    then_clause   JSONB NOT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    fires_count   INT NOT NULL DEFAULT 0,
    last_run_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_rule_ws_enabled
  ON aryx_ontology_rule (workspace_id, enabled);
