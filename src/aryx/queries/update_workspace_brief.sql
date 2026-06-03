UPDATE aryx_workspace
SET brief = %s
WHERE id = %s
RETURNING id, name, description, context, brief, created_at
