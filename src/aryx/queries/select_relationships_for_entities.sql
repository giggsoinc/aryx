SELECT source_entity_id, target_entity_id, name
FROM aryx_relationship
WHERE workspace_id = %s
  AND (source_entity_id = ANY(%s) OR target_entity_id = ANY(%s))
