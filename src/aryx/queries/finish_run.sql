UPDATE aryx_run
   SET status = 'complete', record_count = %s, finished_at = now()
 WHERE run_id = %s
