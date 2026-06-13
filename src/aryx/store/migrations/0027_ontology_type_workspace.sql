-- 0027 — Multi-tenant the ontology type table.
--
-- Pre-existing aryx_ontology_type had no workspace_id column and a
-- UNIQUE(name) constraint that prevented the same type existing in two
-- workspaces. With the DEMO/Default split this caused types to "leak":
-- every workspace saw every type because no filter was possible.
--
-- Fix:
--   1. Add workspace_id NOT NULL DEFAULT 1 (backfills existing rows to
--      workspace 1 — the DEMO workspace — preserving the demo dataset).
--   2. Drop the UNIQUE(name) constraint; replace with UNIQUE(workspace_id, name).
--   3. Index workspace_id for the new GET filter.

ALTER TABLE aryx_ontology_type
    ADD COLUMN IF NOT EXISTS workspace_id BIGINT NOT NULL DEFAULT 1;

ALTER TABLE aryx_ontology_type
    DROP CONSTRAINT IF EXISTS aryx_ontology_type_name_key;

DROP INDEX IF EXISTS aryx_ontology_type_name_key;

ALTER TABLE aryx_ontology_type
    ADD CONSTRAINT aryx_ontology_type_ws_name_key
        UNIQUE (workspace_id, name);

CREATE INDEX IF NOT EXISTS idx_ontology_type_ws
    ON aryx_ontology_type (workspace_id);
