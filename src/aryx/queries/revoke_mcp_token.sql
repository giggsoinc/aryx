UPDATE aryx_mcp_token
SET revoked_at = now()
WHERE id = %s AND revoked_at IS NULL
RETURNING id, label
