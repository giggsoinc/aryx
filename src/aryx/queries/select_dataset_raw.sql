SELECT raw_bytes, format FROM aryx_dataset_version
WHERE workspace_id = %s AND dataset_id = %s AND version = %s
