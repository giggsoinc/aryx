UPDATE aryx_entity
SET attributes = attributes || %s,
    updated_at = now()
WHERE id = %s AND workspace_id = %s
RETURNING attributes
