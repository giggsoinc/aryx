SELECT profile FROM aryx_dataset_profile
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
