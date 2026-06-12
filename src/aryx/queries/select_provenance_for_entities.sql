SELECT m.entity_id, r.source_system, r.source_dataset, r.source_record_id
FROM aryx_entity_member m
JOIN aryx_landed_record r ON r.id = m.landed_record_id
WHERE m.workspace_id = %s AND m.entity_id = ANY(%s)
