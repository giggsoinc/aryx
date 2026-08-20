-- G10 follow-up: llm_verdict was boolean (same/not-same). adjudicate() now
-- returns a rescored confidence in [0, 1], so the column must hold a decimal.
-- migrate.py re-runs every file on every invocation (no applied-migrations
-- table), so this cast is guarded to fire only once, while the column is
-- still boolean — otherwise every re-run would wipe real llm_verdict data
-- back to NULL via USING NULL.
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'aryx_adjudication' AND column_name = 'llm_verdict') = 'boolean' THEN
        ALTER TABLE aryx_adjudication ALTER COLUMN llm_verdict TYPE NUMERIC(4, 3) USING NULL;
    END IF;
END $$;
