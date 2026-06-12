INSERT INTO aryx_run_stage (run_id, stage, status, detail)
VALUES (%s, %s, %s, %s)
ON CONFLICT (run_id, stage)
DO UPDATE SET status = EXCLUDED.status,
              detail = EXCLUDED.detail,
              started_at = CASE WHEN EXCLUDED.status = 'running'
                                THEN now() ELSE aryx_run_stage.started_at END,
              finished_at = CASE WHEN EXCLUDED.status IN ('done', 'failed')
                                 THEN now() ELSE NULL END
