SELECT request_id, schema_version, uploaded_file, domain, objective,
       preferences, validation_status, warnings, errors, created_at,
       brief_context
FROM aryx_user_intent
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
