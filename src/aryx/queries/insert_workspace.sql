INSERT INTO aryx_workspace (name, description)
VALUES (%s, %s)
RETURNING id, name, description, created_at
