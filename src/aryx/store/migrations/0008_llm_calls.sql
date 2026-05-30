-- LLM call log (Increment: observability). Every chat/JSON completion is
-- recorded here so the dashboard can show tokens consumed, latency, and
-- which models are driving cost. Rows are append-only; old rows follow the
-- same 30-day archive cycle as aryx_job.

CREATE TABLE IF NOT EXISTS aryx_llm_call (
    id               BIGSERIAL PRIMARY KEY,
    role             TEXT NOT NULL,
    model            TEXT NOT NULL,
    provider         TEXT NOT NULL DEFAULT 'ollama',
    prompt_tokens    INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms       INTEGER NOT NULL DEFAULT 0,
    source           TEXT NOT NULL DEFAULT 'ask',
    error            TEXT,
    ts               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_call_ts ON aryx_llm_call (ts);
