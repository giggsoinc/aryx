INSERT INTO aryx_dataset_version
    (workspace_id, dataset_id, version, request_id, format, content_hash,
     raw_bytes, raw_snapshot_ref, row_count_estimate, columns, sheets,
     ingestion_status, processing_status, errors, file_name, file_size_bytes)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
