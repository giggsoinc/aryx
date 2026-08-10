-- Persisted LLM choice. One row; UI "Settings" and the Home confirm gate
-- write it; llm_runtime overlays it on env defaults at startup so a
-- container restart never silently reverts the user's model choice.
CREATE TABLE IF NOT EXISTS aryx_llm_config (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    provider text NOT NULL,
    menial_model text NOT NULL,
    answer_model text NOT NULL,
    endpoint text NOT NULL,
    api_key text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);
