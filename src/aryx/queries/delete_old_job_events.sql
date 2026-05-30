DELETE FROM aryx_job_event WHERE ts < now() - (%s * interval '1 day')
