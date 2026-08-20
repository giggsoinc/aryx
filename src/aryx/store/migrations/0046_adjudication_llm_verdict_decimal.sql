-- G10 follow-up: llm_verdict was boolean (same/not-same). adjudicate() now
-- returns a rescored confidence in [0, 1], so the column must hold a decimal.
-- migrate.py re-runs every file on every invocation (no applied-migrations
-- table), so this cast is guarded to fire only once, while the column is
-- still boolean.
--
-- Existing boolean verdicts are mapped onto the confidence scale instead of
-- discarded: true ("same") -> 1.0, false ("not same") -> 0.0, unset stays
-- NULL. This also keeps adjudication_stats.sql's `llm_verdict >= 0.95`
-- agreement check meaningful for historical rows instead of losing the
-- signal entirely.
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'aryx_adjudication' AND column_name = 'llm_verdict') = 'boolean' THEN
        ALTER TABLE aryx_adjudication ALTER COLUMN llm_verdict TYPE NUMERIC(4, 3)
            USING CASE WHEN llm_verdict IS TRUE THEN 1.0
                       WHEN llm_verdict IS FALSE THEN 0.0
                       ELSE NULL END;
    END IF;
END $$;
