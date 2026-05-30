DELETE FROM aryx_job WHERE finished_at IS NOT NULL
  AND finished_at < now() - (%s * interval '1 day')
