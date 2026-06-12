UPDATE aryx_adjudication
SET status = %s, decided_by = %s, decided_at = now()
WHERE id = %s AND status = 'pending'
RETURNING id, workspace_id, run_id, left_record_id, right_record_id,
          score, llm_verdict, status, decided_by
