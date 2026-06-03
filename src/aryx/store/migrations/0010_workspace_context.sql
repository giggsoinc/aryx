-- Workspace-level business context: a single text field shared by every
-- ingest tab (DB + Documents + future API/MCP), every Ask question, every
-- Graph view, and the Ontology discovery agent. Replaces per-tab context
-- inputs in ingest_files / ingest_rdb so the agent always knows what the
-- workspace is for.

ALTER TABLE aryx_workspace
  ADD COLUMN IF NOT EXISTS context TEXT NOT NULL DEFAULT '';
