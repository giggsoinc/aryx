-- Mark "running" jobs with no checkpoint for N minutes as failed.
-- A background ingest task dies silently when its container restarts or the
-- process is killed; the row would otherwise claim "running" forever.
UPDATE aryx_job
SET status = 'failed',
    error = 'no checkpoint for ' || %s || ' minutes — the ingest process '
            'likely died (container restart / out of memory). Re-run the upload.',
    finished_at = now()
WHERE status = 'running'
  AND updated_at < now() - make_interval(mins => %s)
RETURNING job_id
