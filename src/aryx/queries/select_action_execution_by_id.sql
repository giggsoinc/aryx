SELECT e.id, e.workspace_id, e.action_id, e.entity_id, e.params, e.status,
       a.definition, a.enabled
FROM aryx_action_execution e
JOIN aryx_action a ON a.id = e.action_id
WHERE e.id = %s
