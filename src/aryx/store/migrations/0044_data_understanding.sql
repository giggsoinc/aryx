-- Data understanding — Aryx's read-only reading of the ingested data.
--
-- Architecture (restored from v1.5.3, regressed in 1.8.0): the CUSTOMER
-- authors the brief BEFORE any upload. `aryx_workspace.brief` (migration
-- 0016) is therefore customer-owned and must never be overwritten by a
-- model. What the pipeline infers from samples after upload lands here
-- instead, and is surfaced as a read-only "what we understood" info tab.
--
-- Shape: {"summary": str, "brief": {...}, "graph_plan": {...},
--         "source_files": [str], "generated_at": iso8601, "fallback": bool}
-- JSONB so the shape can evolve without a schema change.

ALTER TABLE aryx_workspace
  ADD COLUMN IF NOT EXISTS data_understanding JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Provenance for `brief`: 'customer' when a human authored it before
-- ingest, 'derived' when it was back-filled from data because the customer
-- skipped the brief step. Downstream gates read this to know whether the
-- brief is authoritative.
ALTER TABLE aryx_workspace
  ADD COLUMN IF NOT EXISTS brief_source TEXT NOT NULL DEFAULT 'customer';
