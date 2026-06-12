INSERT INTO aryx_adjudication
    (workspace_id, run_id, left_record_id, right_record_id,
     score, llm_verdict, llm_reason, status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id
