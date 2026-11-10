DELETE FROM aryx_schema_mapping
WHERE run_id IN (SELECT run_id FROM aryx_run WHERE workspace_id = %s)
