INSERT INTO aryx_graph_profile
    (workspace_id, graph_profile_id, graph_id, graph_version,
     entity_count, relationship_count, path_count, profile_status, profile)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, graph_id, graph_version) DO UPDATE SET
    graph_profile_id   = EXCLUDED.graph_profile_id,
    entity_count       = EXCLUDED.entity_count,
    relationship_count = EXCLUDED.relationship_count,
    path_count         = EXCLUDED.path_count,
    profile_status     = EXCLUDED.profile_status,
    profile            = EXCLUDED.profile,
    created_at         = NOW()
