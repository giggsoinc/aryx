-- Aryx resolved entities (Increment 5b). Canonical entities + provenance
-- members linking each entity back to the landed records it merged.
-- Additive migration; never edit earlier migrations.

CREATE TABLE IF NOT EXISTS aryx_entity (
    id            BIGSERIAL PRIMARY KEY,
    ontology_type TEXT NOT NULL,
    attributes    JSONB NOT NULL DEFAULT '{}',
    confidence    REAL NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aryx_entity_member (
    id               BIGSERIAL PRIMARY KEY,
    entity_id        BIGINT NOT NULL REFERENCES aryx_entity (id),
    landed_record_id BIGINT NOT NULL REFERENCES aryx_landed_record (id),
    confidence       REAL NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_member_entity ON aryx_entity_member (entity_id);
CREATE INDEX IF NOT EXISTS idx_member_record ON aryx_entity_member (landed_record_id);
