SELECT request_id, schema_version, uploaded_file, domain, objective,
       preferences, validation_status, warnings, errors, created_at
FROM aryx_user_intent
WHERE workspace_id = %s AND request_id = %s
