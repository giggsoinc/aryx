SELECT id, workspace_id, name, source_type, target_type,
       description, created_at
FROM aryx_relationship_type
WHERE workspace_id = %(workspace_id)s
ORDER BY created_at DESC
