INSERT INTO aryx_user_intent
    (workspace_id, request_id, schema_version, uploaded_file, domain, objective,
     preferences, validation_status, warnings, errors)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, request_id) DO UPDATE SET
    schema_version    = EXCLUDED.schema_version,
    uploaded_file     = EXCLUDED.uploaded_file,
    domain            = EXCLUDED.domain,
    objective         = EXCLUDED.objective,
    preferences       = EXCLUDED.preferences,
    validation_status = EXCLUDED.validation_status,
    warnings          = EXCLUDED.warnings,
    errors            = EXCLUDED.errors
RETURNING created_at
