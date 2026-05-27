INSERT INTO aryx_run (source_system, source_dataset)
VALUES (%s, %s)
RETURNING run_id
