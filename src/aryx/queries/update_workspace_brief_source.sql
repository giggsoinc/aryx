UPDATE aryx_workspace
SET brief_source = %s
WHERE id = %s
RETURNING id, brief_source
