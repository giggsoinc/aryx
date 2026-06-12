INSERT INTO aryx_action (workspace_id, name, definition, enabled, created_by)
VALUES (%s, %s, %s, %s, %s)
RETURNING id
