INSERT INTO aryx_ingest_question
    (workspace_id, job_id, kind, prompt, options_json, suggested)
VALUES (%(workspace_id)s, %(job_id)s, %(kind)s, %(prompt)s,
        %(options_json)s::jsonb, %(suggested)s)
RETURNING id
