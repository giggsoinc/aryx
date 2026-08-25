DELETE FROM aryx_relationship d
USING aryx_relationship k
WHERE d.workspace_id = %s
  AND k.workspace_id = d.workspace_id
  AND d.id != k.id
  AND d.name = k.name
  AND (
    (d.source_entity_id = %s AND k.source_entity_id = %s AND d.target_entity_id = k.target_entity_id)
    OR
    (d.target_entity_id = %s AND k.target_entity_id = %s AND d.source_entity_id = k.source_entity_id)
  )
