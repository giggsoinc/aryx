SELECT stage, pct, detail, ts
FROM aryx_job_event
WHERE job_id = %s
ORDER BY ts DESC, id DESC
LIMIT 80
