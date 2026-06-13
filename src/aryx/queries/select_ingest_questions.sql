SELECT id, workspace_id, job_id, kind, prompt, options_json, suggested,
       status, answer, answered_by, created_at, answered_at
FROM aryx_ingest_question
WHERE workspace_id = %(workspace_id)s
  AND (%(status)s = '' OR status = %(status)s)
ORDER BY created_at DESC
LIMIT %(limit)s
