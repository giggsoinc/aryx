SELECT stage, status, started_at, finished_at, detail
FROM aryx_run_stage
WHERE run_id = %s
ORDER BY started_at
