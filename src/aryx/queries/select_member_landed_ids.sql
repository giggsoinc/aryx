SELECT entity_id, landed_record_id
FROM aryx_entity_member
WHERE workspace_id = %s AND entity_id = ANY(%s)
