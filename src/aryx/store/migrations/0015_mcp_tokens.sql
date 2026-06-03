-- Bearer tokens for the MCP /mcp endpoint. The plain token is only shown
-- once at create time; only the SHA-256 hash is stored. Verification hashes
-- the incoming Authorization header and looks it up.

CREATE TABLE IF NOT EXISTS aryx_mcp_token (
    id            BIGSERIAL PRIMARY KEY,
    label         TEXT NOT NULL DEFAULT '',
    token_hash    TEXT NOT NULL UNIQUE,
    prefix        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ,
    revoked_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_mcp_token_active
  ON aryx_mcp_token (token_hash) WHERE revoked_at IS NULL;
