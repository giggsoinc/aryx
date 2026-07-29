SELECT profile FROM aryx_dataset_profile
WHERE workspace_id = %s AND dataset_id = %s
ORDER BY created_at DESC
LIMIT 1
