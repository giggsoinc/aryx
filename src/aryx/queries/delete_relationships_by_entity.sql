DELETE FROM aryx_relationship
WHERE workspace_id = %s AND (source_entity_id = %s OR target_entity_id = %s)
