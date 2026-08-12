-- Mark "running" jobs with no checkpoint for N minutes as failed.
-- A background ingest task dies silently when its container restarts or the
-- process is killed; the row would otherwise claim "running" forever.
-- Long Resolve stages heartbeat every ~45s; default N is 30 minutes so
-- large ER runs are not false-failed while still healthy.
UPDATE aryx_job
SET status = 'failed',
    error = 'no checkpoint for ' || %s || ' minutes — the ingest process '
            'likely died (container restart / out of memory). '
            'If run_id is set, use Resume on Observability; otherwise re-upload.',
    finished_at = now()
WHERE status = 'running'
  AND updated_at < now() - make_interval(mins => %s)
RETURNING job_id
