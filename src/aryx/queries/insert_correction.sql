INSERT INTO aryx_correction (workspace_id, kind, subject, object, detail)
VALUES (%s, %s, %s, %s, %s)
RETURNING id, created_at
