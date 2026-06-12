SELECT id, payload, source_system, cleaned_at
FROM aryx_landed_record
WHERE run_id = %s AND workspace_id = %s
