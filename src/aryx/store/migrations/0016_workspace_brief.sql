-- Knowledge-modelling brief — METHONTOLOGY-style competency questions
-- captured BEFORE ingest so the lightweight ontology is grounded in
-- declared intent (domain, aim, objectives, scope, roles).
--
-- Stored as JSONB so the structure can evolve without a schema change.
-- The free-text `context` column (migration 0010) stays as an override /
-- free-text supplement; the pipeline uses both — serialise(brief) +
-- context — when building extraction prompts.

ALTER TABLE aryx_workspace
  ADD COLUMN IF NOT EXISTS brief JSONB NOT NULL DEFAULT '{}'::jsonb;
