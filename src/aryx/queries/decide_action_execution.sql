UPDATE aryx_action_execution
SET status = %s, decided_by = %s, decided_at = now()
WHERE id = %s AND status = 'pending'
RETURNING id, action_id, entity_id, params, status
