UPDATE aryx_mcp_token
SET last_used_at = now()
WHERE token_hash = %s AND revoked_at IS NULL
