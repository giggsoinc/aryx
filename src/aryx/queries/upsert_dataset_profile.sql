INSERT INTO aryx_dataset_profile
    (workspace_id, dataset_profile_id, dataset_id, dataset_version,
     row_count, column_count, profile_status, profile)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id, dataset_version) DO UPDATE SET
    dataset_profile_id = EXCLUDED.dataset_profile_id,
    row_count          = EXCLUDED.row_count,
    column_count       = EXCLUDED.column_count,
    profile_status     = EXCLUDED.profile_status,
    profile            = EXCLUDED.profile,
    created_at         = NOW()
