INSERT INTO aryx_projected_entity (workspace_id, entity_id)
VALUES (%s, %s)
ON CONFLICT DO NOTHING
