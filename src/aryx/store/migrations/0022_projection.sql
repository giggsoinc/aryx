-- G8 incremental projection: watermark + projected-id side table.
-- Dirty-set computation happens in Postgres (never diff the graph itself):
-- dirty = entities created/updated since the watermark; tombstones = ids in
-- the side table that no longer exist in aryx_entity.

ALTER TABLE aryx_entity
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS aryx_projection_state (
    workspace_id      BIGINT PRIMARY KEY,
    last_projected_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS aryx_projected_entity (
    workspace_id BIGINT NOT NULL,
    entity_id    BIGINT NOT NULL,
    PRIMARY KEY (workspace_id, entity_id)
);
