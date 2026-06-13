UPDATE aryx_ingest_question
SET status = 'answered', answer = %(answer)s, answered_by = %(answered_by)s,
    answered_at = NOW()
WHERE id = %(id)s
RETURNING id, status, answer
