INSERT INTO aryx_job_archive (job_id, source_system, source_dataset, status,
    stage, pct, detail, run_id, error, started_at, updated_at, finished_at)
SELECT job_id, source_system, source_dataset, status, stage, pct, detail,
       run_id, error, started_at, updated_at, finished_at
FROM aryx_job
WHERE finished_at IS NOT NULL
  AND finished_at < now() - (%s * interval '1 day')
ON CONFLICT (job_id) DO NOTHING
