SELECT id, payload, source_system, cleaned_at
FROM aryx_landed_record
WHERE workspace_id = %s AND id = ANY(%s)
