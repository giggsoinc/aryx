SELECT status, count(*) FROM aryx_job WHERE workspace_id = %s GROUP BY status
