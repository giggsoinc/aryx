SELECT entity_id
FROM aryx_entity_member
WHERE workspace_id = %s AND landed_record_id = %s
ORDER BY entity_id
LIMIT 1
