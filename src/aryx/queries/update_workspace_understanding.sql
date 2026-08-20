UPDATE aryx_workspace
SET data_understanding = %s
WHERE id = %s
RETURNING id, data_understanding
