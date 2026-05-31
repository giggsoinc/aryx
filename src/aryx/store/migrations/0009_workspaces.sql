-- Workspaces (logical + physical isolation). Each workspace owns a LIST
-- partition of the resolution tables (drop partition = instant physical purge,
-- partition pruning = localized search) and its own FalkorDB named graph.
-- The conversion runs once, guarded by pg_partitioned_table; restarts are no-ops.
-- Inter-table FKs are dropped: this is a rebuildable projection the app keeps
-- consistent, and FK-free partitions stay simple. Existing data is disposable.

CREATE TABLE IF NOT EXISTS aryx_workspace (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO aryx_workspace (id, name, description)
VALUES (1, 'Default', 'Original workspace')
ON CONFLICT (id) DO NOTHING;

-- Advance the serial past the hand-seeded Default so generated ids start at 2.
SELECT setval(pg_get_serial_sequence('aryx_workspace', 'id'),
              (SELECT max(id) FROM aryx_workspace));

ALTER TABLE aryx_run ADD COLUMN IF NOT EXISTS workspace_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE aryx_job ADD COLUMN IF NOT EXISTS workspace_id BIGINT NOT NULL DEFAULT 1;

DO $mig$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_partitioned_table pt
    JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'aryx_entity'
  ) THEN
    DROP TABLE IF EXISTS aryx_relationship CASCADE;
    DROP TABLE IF EXISTS aryx_entity_member CASCADE;
    DROP TABLE IF EXISTS aryx_entity CASCADE;
    DROP TABLE IF EXISTS aryx_landed_record CASCADE;

    CREATE TABLE aryx_landed_record (
        id               BIGSERIAL,
        workspace_id     BIGINT NOT NULL,
        run_id           BIGINT NOT NULL,
        source_system    TEXT NOT NULL,
        source_dataset   TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        payload          JSONB NOT NULL,
        cleaned_at       TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (id, workspace_id)
    ) PARTITION BY LIST (workspace_id);

    CREATE TABLE aryx_entity (
        id            BIGSERIAL,
        workspace_id  BIGINT NOT NULL,
        ontology_type TEXT NOT NULL,
        attributes    JSONB NOT NULL DEFAULT '{}',
        confidence    REAL NOT NULL DEFAULT 0,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (id, workspace_id)
    ) PARTITION BY LIST (workspace_id);

    CREATE TABLE aryx_entity_member (
        id               BIGSERIAL,
        workspace_id     BIGINT NOT NULL,
        entity_id        BIGINT NOT NULL,
        landed_record_id BIGINT NOT NULL,
        confidence       REAL NOT NULL DEFAULT 1,
        PRIMARY KEY (id, workspace_id)
    ) PARTITION BY LIST (workspace_id);

    CREATE TABLE aryx_relationship (
        id               BIGSERIAL,
        workspace_id     BIGINT NOT NULL,
        source_entity_id BIGINT NOT NULL,
        target_entity_id BIGINT NOT NULL,
        name             TEXT NOT NULL,
        confidence       REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (id, workspace_id)
    ) PARTITION BY LIST (workspace_id);

    CREATE TABLE aryx_landed_record_ws1 PARTITION OF aryx_landed_record FOR VALUES IN (1);
    CREATE TABLE aryx_entity_ws1 PARTITION OF aryx_entity FOR VALUES IN (1);
    CREATE TABLE aryx_entity_member_ws1 PARTITION OF aryx_entity_member FOR VALUES IN (1);
    CREATE TABLE aryx_relationship_ws1 PARTITION OF aryx_relationship FOR VALUES IN (1);

    CREATE INDEX idx_landed_ws_run ON aryx_landed_record (workspace_id, run_id);
    CREATE INDEX idx_entity_ws_type ON aryx_entity (workspace_id, ontology_type);
    CREATE INDEX idx_member_ws_entity ON aryx_entity_member (workspace_id, entity_id);
    CREATE INDEX idx_member_ws_landed ON aryx_entity_member (workspace_id, landed_record_id);
    CREATE INDEX idx_rel_ws_source ON aryx_relationship (workspace_id, source_entity_id);
    CREATE INDEX idx_rel_ws_target ON aryx_relationship (workspace_id, target_entity_id);
  END IF;
END
$mig$;
