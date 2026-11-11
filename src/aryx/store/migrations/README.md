# Migrations

SQL files here are applied in filename order by `aryx.store.migrate.apply_migrations`
(API startup, plus a cheap no-op on later calls).

## Rules

1. **Never edit a migration that has shipped.** Each file is recorded in the
   `aryx_schema_migration` table the first time it fully succeeds and is never run
   again. Editing an applied file changes nothing on any database that already
   recorded it. To change the schema, add a **new** numbered file
   (`00NN_what_it_does.sql`).
2. **Make every statement safe to re-run** (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).
   A file is retried until all of its statements succeed. A statement that fails
   with "already exists" (SQLSTATE 42701 / 42710 / 42P07) counts as applied.
3. **A file with a permanently failing statement** (for example `CREATE EXTENSION
   vector` on a Postgres without pgvector) is left unrecorded and retried at the
   next process start. It is not retried on every request, and a `MIGRATION_UNRECORDED`
   warning lists it once.
4. **Never move the workspace id sequence backwards.** Reusing a deleted workspace's id
   lets an orphaned background job write into the new workspace (see `0009`).
