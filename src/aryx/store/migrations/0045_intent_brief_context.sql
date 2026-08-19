-- 0045 — carry the whole customer brief into C01 intent.
--
-- The brief is authored BEFORE upload and is the customer's statement of
-- what they want. Until now only `domain` and `objective` survived the
-- brief -> intent mapping (see intent/from_brief.py), so planning and
-- dashboard composition never saw scope, objectives, proof questions, or
-- any role past the first. UserIntent schema 1.1 adds `brief_context` to
-- close that gap; this column persists it.
--
-- Existing rows keep '{}' and stay schema_version '1.0' — readers treat a
-- missing brief_context as "brief-blind capture", which is exactly what
-- those rows were.

ALTER TABLE aryx_user_intent
  ADD COLUMN IF NOT EXISTS brief_context JSONB NOT NULL DEFAULT '{}'::jsonb;
