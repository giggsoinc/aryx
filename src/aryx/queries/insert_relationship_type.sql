INSERT INTO aryx_relationship_type
    (workspace_id, name, source_type, target_type, description)
VALUES (%(workspace_id)s, %(name)s, %(source_type)s,
        %(target_type)s, %(description)s)
ON CONFLICT (workspace_id, source_type, name, target_type)
DO UPDATE SET description = EXCLUDED.description
RETURNING id, workspace_id, name, source_type, target_type,
          description, created_at
