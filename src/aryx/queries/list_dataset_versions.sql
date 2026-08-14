SELECT request_id, dataset_id, version, format, content_hash, raw_snapshot_ref,
       row_count_estimate, columns, sheets, ingestion_status, processing_status,
       errors, file_name, file_size_bytes, created_at
FROM aryx_dataset_version
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
