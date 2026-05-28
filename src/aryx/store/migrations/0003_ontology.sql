-- Aryx ontology (Increment 5a). Canonical types + source-to-ontology mappings.
-- New types start status='proposed' and pass the human review gate before use.
-- Additive migration; never edit 0001 or 0002.

CREATE TABLE IF NOT EXISTS aryx_ontology_type (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    attributes JSONB NOT NULL DEFAULT '[]',
    status     TEXT NOT NULL DEFAULT 'proposed',
    source     TEXT NOT NULL DEFAULT 'agent',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS aryx_schema_mapping (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             BIGINT REFERENCES aryx_run (run_id),
    source_system      TEXT NOT NULL,
    source_dataset     TEXT NOT NULL,
    source_field       TEXT,
    ontology_type      TEXT NOT NULL,
    ontology_attribute TEXT,
    confidence         REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mapping_run ON aryx_schema_mapping (run_id);
