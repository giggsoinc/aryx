-- Link a discovery run to a live job as soon as records are landed (resume).
UPDATE aryx_job
   SET run_id = %s, updated_at = now()
 WHERE job_id = %s
   AND status IN ('queued', 'running', 'failed', 'cancelled')
