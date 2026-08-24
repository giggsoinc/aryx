SELECT DISTINCT ON (landed_record_id) landed_record_id, entity_id
FROM aryx_entity_member
WHERE workspace_id = %s AND landed_record_id = ANY(%s)
ORDER BY landed_record_id, entity_id
