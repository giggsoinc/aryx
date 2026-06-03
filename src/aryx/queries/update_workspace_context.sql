UPDATE aryx_workspace
SET context = %s
WHERE id = %s
RETURNING id, name, description, context, created_at
