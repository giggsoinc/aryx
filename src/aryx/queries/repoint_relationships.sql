UPDATE aryx_relationship
SET source_entity_id = CASE WHEN source_entity_id = %s THEN %s ELSE source_entity_id END,
    target_entity_id = CASE WHEN target_entity_id = %s THEN %s ELSE target_entity_id END
WHERE workspace_id = %s AND (source_entity_id = %s OR target_entity_id = %s)
