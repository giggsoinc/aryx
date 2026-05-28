-- Aryx relationships (Increment 5c). Typed edges between resolved entities.
-- Additive migration; never edit earlier migrations.

CREATE TABLE IF NOT EXISTS aryx_relationship (
    id               BIGSERIAL PRIMARY KEY,
    source_entity_id BIGINT NOT NULL REFERENCES aryx_entity (id),
    target_entity_id BIGINT NOT NULL REFERENCES aryx_entity (id),
    name             TEXT NOT NULL,
    confidence       REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rel_source ON aryx_relationship (source_entity_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON aryx_relationship (target_entity_id);
