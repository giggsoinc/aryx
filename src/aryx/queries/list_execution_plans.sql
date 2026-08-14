SELECT plan FROM aryx_execution_plan
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
