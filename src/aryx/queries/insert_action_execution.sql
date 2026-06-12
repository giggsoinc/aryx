INSERT INTO aryx_action_execution
    (workspace_id, action_id, entity_id, params, status, requested_by)
VALUES (%s, %s, %s, %s, %s, %s)
RETURNING id
