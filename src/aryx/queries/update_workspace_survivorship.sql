UPDATE aryx_workspace
SET survivorship = %s
WHERE id = %s
RETURNING id, survivorship
