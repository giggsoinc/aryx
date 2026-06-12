SELECT DISTINCT m.block_key
FROM aryx_block_member m
LEFT JOIN aryx_block_done d
       ON d.run_id = m.run_id AND d.block_key = m.block_key
WHERE m.run_id = %s AND d.block_key IS NULL
ORDER BY m.block_key
