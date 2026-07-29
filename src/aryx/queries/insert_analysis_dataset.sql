INSERT INTO aryx_analysis_dataset
    (workspace_id, analysis_dataset_id, source_dataset_id, source_dataset_version,
     status, row_count, result)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, source_dataset_id, source_dataset_version)
DO UPDATE SET analysis_dataset_id = EXCLUDED.analysis_dataset_id,
              status = EXCLUDED.status, row_count = EXCLUDED.row_count,
              result = EXCLUDED.result, created_at = NOW()
