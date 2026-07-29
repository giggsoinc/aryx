INSERT INTO aryx_spec_validation
    (workspace_id, validation_id, attempt, spec_id, status, report)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, validation_id, attempt)
DO UPDATE SET spec_id = EXCLUDED.spec_id, status = EXCLUDED.status,
              report = EXCLUDED.report, created_at = NOW()
