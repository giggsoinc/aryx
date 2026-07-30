SELECT model FROM aryx_dashboard_model
WHERE workspace_id = %s AND dataset_id = %s
ORDER BY created_at DESC
LIMIT 1
