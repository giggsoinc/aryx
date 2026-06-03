INSERT INTO aryx_workspace (name, description, context)
VALUES (%s, %s, %s)
RETURNING id, name, description, context, created_at
