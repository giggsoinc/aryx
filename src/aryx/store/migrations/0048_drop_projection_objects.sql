-- Remove the objects only the deleted FalkorDB projector used.
--
-- aryx_projection_state / aryx_projected_entity held the projector's watermark
-- and projected-id list; aryx_entity.updated_at existed so its dirty-set could
-- find changed entities. The graph is now read live from the relational tables,
-- so nothing reads or writes any of them.
--
-- apply_migrations re-runs every file on every call, so each step is guarded by
-- an existence check: after the first run this is a no-op that takes no table
-- lock. Migration 0022, which used to create these objects, no longer does.
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables
              WHERE schemaname = current_schema()
                AND tablename = 'aryx_projection_state') THEN
    DROP TABLE aryx_projection_state;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_tables
              WHERE schemaname = current_schema()
                AND tablename = 'aryx_projected_entity') THEN
    DROP TABLE aryx_projected_entity;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = current_schema()
                AND table_name = 'aryx_entity'
                AND column_name = 'updated_at') THEN
    ALTER TABLE aryx_entity DROP COLUMN updated_at;
  END IF;
END
$mig$;
