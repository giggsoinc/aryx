SELECT report FROM aryx_spec_validation
WHERE workspace_id = %s AND validation_id = %s
ORDER BY attempt DESC
LIMIT 1
