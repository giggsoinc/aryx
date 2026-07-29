INSERT INTO aryx_semantic_profile
    (workspace_id, semantic_profile_id, dataset_id, dataset_version, domain,
     annotation_count, unresolved_count, profile_status, profile)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, dataset_id, dataset_version) DO UPDATE SET
    semantic_profile_id = EXCLUDED.semantic_profile_id,
    domain              = EXCLUDED.domain,
    annotation_count    = EXCLUDED.annotation_count,
    unresolved_count    = EXCLUDED.unresolved_count,
    profile_status      = EXCLUDED.profile_status,
    profile             = EXCLUDED.profile,
    created_at          = NOW()
