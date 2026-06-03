INSERT INTO aryx_workspace (name, description, context, brief)
VALUES (%s, %s, %s, %s)
RETURNING id, name, description, context, brief, created_at
