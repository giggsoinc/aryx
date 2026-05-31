SELECT id, payload
FROM aryx_landed_record
WHERE run_id = %s AND workspace_id = %s
