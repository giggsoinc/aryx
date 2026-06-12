SELECT p.entity_id
FROM aryx_projected_entity p
WHERE p.workspace_id = %s
EXCEPT
SELECT e.id
FROM aryx_entity e
WHERE e.workspace_id = %s
