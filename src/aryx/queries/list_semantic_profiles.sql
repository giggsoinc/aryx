SELECT profile FROM aryx_semantic_profile
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
