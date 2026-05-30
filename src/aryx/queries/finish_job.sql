UPDATE aryx_job
   SET status = %s, run_id = %s, error = %s, pct = 100,
       finished_at = now(), updated_at = now()
 WHERE job_id = %s
