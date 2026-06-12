SELECT e.id, a.name, e.entity_id, e.params, e.status,
       e.requested_by, e.decided_by, e.decided_at, e.applied_at,
       e.effect_log, e.created_at
FROM aryx_action_execution e
JOIN aryx_action a ON a.id = e.action_id
WHERE e.workspace_id = %s AND e.status = %s
ORDER BY e.id
LIMIT %s OFFSET %s
