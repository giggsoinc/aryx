INSERT INTO aryx_dataset (workspace_id, dataset_id, request_id, file_name)
VALUES (%s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id) DO UPDATE SET
    request_id = EXCLUDED.request_id,
    file_name  = EXCLUDED.file_name
