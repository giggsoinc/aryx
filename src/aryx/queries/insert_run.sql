INSERT INTO aryx_run (workspace_id, source_system, source_dataset)
VALUES (%s, %s, %s)
RETURNING run_id
