SELECT id FROM aryx_mcp_token
WHERE token_hash = %s AND revoked_at IS NULL
LIMIT 1
