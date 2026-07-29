SELECT result FROM aryx_dashboard_spec
WHERE workspace_id = %s AND dataset_id = %s
ORDER BY created_at DESC
LIMIT 1
