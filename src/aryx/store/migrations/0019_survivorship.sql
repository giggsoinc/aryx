-- G3 survivorship: per-attribute conflict audit + workspace merge policy.
-- Every disagreement between cluster members is recorded with the losing
-- values and the strategy that decided the winner — the "why does the golden
-- record say X?" answer. Idempotent per house style.

CREATE TABLE IF NOT EXISTS aryx_attribute_conflict (
    id             BIGSERIAL PRIMARY KEY,
    workspace_id   BIGINT NOT NULL,
    entity_id      BIGINT NOT NULL,
    attribute      TEXT NOT NULL,
    winning_value  JSONB,
    losing_values  JSONB NOT NULL,   -- [{value, source_system, record_id}]
    strategy       TEXT NOT NULL,
    decided_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conflict_entity
    ON aryx_attribute_conflict (workspace_id, entity_id);

-- Workspace-scoped survivorship policy (JSON authored by humans or skills).
ALTER TABLE aryx_workspace
    ADD COLUMN IF NOT EXISTS survivorship JSONB NOT NULL DEFAULT '{}';
