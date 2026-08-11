SELECT id, kind, subject, object, detail, created_at
FROM aryx_correction WHERE workspace_id = %s ORDER BY created_at DESC
