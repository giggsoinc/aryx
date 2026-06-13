SELECT status, COUNT(*) FROM aryx_ingest_question
WHERE workspace_id = %(workspace_id)s
  AND (%(job_id)s = '' OR job_id = %(job_id)s)
GROUP BY status
