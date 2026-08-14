SELECT plan FROM aryx_execution_plan
WHERE workspace_id = %s AND dataset_id = %s
ORDER BY created_at DESC
LIMIT 1
