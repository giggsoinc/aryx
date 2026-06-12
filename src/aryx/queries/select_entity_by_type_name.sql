SELECT id
FROM aryx_entity
WHERE workspace_id = %s AND ontology_type = %s
  AND attributes->>'name' = %s
ORDER BY id
LIMIT 1
