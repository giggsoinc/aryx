UPDATE aryx_entity
SET attributes = attributes || %s
WHERE id = %s AND workspace_id = %s
RETURNING attributes
