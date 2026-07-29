UPDATE aryx_dataset_version
SET processing_status = %s, errors = %s
WHERE workspace_id = %s AND dataset_id = %s AND version = %s
