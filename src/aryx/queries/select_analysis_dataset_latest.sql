SELECT result FROM aryx_analysis_dataset
WHERE workspace_id = %s AND source_dataset_id = %s
ORDER BY created_at DESC
LIMIT 1
