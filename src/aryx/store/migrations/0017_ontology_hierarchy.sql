-- Aryx ontology hierarchy (Night 1, Phase 1).
-- Adds a single parent_type column to support Protégé-style subClassOf semantics.
-- Self-referential by name (matches existing UNIQUE constraint on name).
-- Additive only — existing rows get NULL parent (root types).

ALTER TABLE aryx_ontology_type
    ADD COLUMN IF NOT EXISTS parent_type TEXT
        REFERENCES aryx_ontology_type (name)
        ON UPDATE CASCADE ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ontology_type_parent
    ON aryx_ontology_type (parent_type)
    WHERE parent_type IS NOT NULL;
