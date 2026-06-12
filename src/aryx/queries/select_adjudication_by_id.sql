SELECT id, workspace_id, run_id, left_record_id, right_record_id, score,
       llm_verdict, llm_reason, status, decided_by, decided_at
FROM aryx_adjudication
WHERE id = %s
