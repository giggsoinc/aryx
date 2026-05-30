UPDATE aryx_job
   SET stage = %s, pct = %s, detail = %s, status = 'running', updated_at = now()
 WHERE job_id = %s
