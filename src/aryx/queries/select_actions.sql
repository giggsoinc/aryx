SELECT id, name, definition, enabled, created_by, created_at
FROM aryx_action
WHERE workspace_id = %s AND superseded_by IS NULL
ORDER BY name
