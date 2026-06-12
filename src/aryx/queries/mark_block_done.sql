INSERT INTO aryx_block_done (run_id, block_key)
VALUES (%s, %s)
ON CONFLICT DO NOTHING
