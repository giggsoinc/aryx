DELETE FROM aryx_field_tag
WHERE run_id IN (SELECT run_id FROM aryx_run WHERE workspace_id = %s)
