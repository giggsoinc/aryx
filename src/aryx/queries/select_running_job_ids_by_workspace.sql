SELECT job_id FROM aryx_job
 WHERE workspace_id = %s
   AND status NOT IN ('complete', 'failed', 'cancelled', 'blocked')
