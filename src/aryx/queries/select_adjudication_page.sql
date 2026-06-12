SELECT id, run_id, left_record_id, right_record_id, score,
       llm_verdict, llm_reason, status, decided_by, decided_at, created_at
FROM aryx_adjudication
WHERE workspace_id = %s AND status = %s
ORDER BY id
LIMIT %s OFFSET %s
