SELECT job_id, source_system, source_dataset, status, stage, pct, detail,
       run_id, error, started_at, updated_at, finished_at
FROM aryx_job
ORDER BY started_at DESC
LIMIT 50
