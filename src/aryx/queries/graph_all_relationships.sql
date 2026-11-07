-- Every distinct edge whose endpoints both exist; the last column flags
-- reasoning-engine (inferred) edges.
SELECT e.source_entity_id, e.target_entity_id, e.name, e.inferred
FROM (
  SELECT r.source_entity_id, r.target_entity_id, r.name, false AS inferred
    FROM aryx_relationship r WHERE r.workspace_id = %(ws)s
  UNION
  SELECT i.source_entity_id, i.target_entity_id, i.name, true
    FROM aryx_inferred_relationship i WHERE i.workspace_id = %(ws)s
) e
JOIN aryx_entity s ON s.workspace_id = %(ws)s AND s.id = e.source_entity_id
JOIN aryx_entity t ON t.workspace_id = %(ws)s AND t.id = e.target_entity_id
ORDER BY 1, 2, 3, 4
