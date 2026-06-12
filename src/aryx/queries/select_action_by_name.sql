SELECT id, name, definition, enabled
FROM aryx_action
WHERE workspace_id = %s AND name = %s AND superseded_by IS NULL
ORDER BY id DESC
LIMIT 1
