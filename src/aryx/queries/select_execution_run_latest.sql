SELECT run FROM aryx_execution_run
WHERE workspace_id = %s AND dataset_id = %s
ORDER BY created_at DESC
LIMIT 1
