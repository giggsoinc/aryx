INSERT INTO aryx_mcp_token (label, token_hash, prefix)
VALUES (%s, %s, %s)
RETURNING id, label, prefix, created_at
