-- A -[name]-> X -[name]-> B  =>  A -[name]-> B, over asserted edges only.
-- Endpoints differ and no edge is used twice; pairs already asserted are skipped.
INSERT INTO aryx_inferred_relationship
    (workspace_id, source_entity_id, target_entity_id, name, rule_name)
SELECT DISTINCT %(ws)s, e1.source_entity_id, e2.target_entity_id, %(name)s, %(rule)s
FROM aryx_relationship e1
JOIN aryx_relationship e2
  ON e2.workspace_id = %(ws)s AND e2.name = %(name)s
 AND e2.source_entity_id = e1.target_entity_id AND e2.id <> e1.id
JOIN aryx_entity s ON s.workspace_id = %(ws)s AND s.id = e1.source_entity_id
JOIN aryx_entity t ON t.workspace_id = %(ws)s AND t.id = e2.target_entity_id
WHERE e1.workspace_id = %(ws)s AND e1.name = %(name)s
  AND e1.source_entity_id <> e2.target_entity_id
  AND NOT EXISTS (SELECT 1 FROM aryx_relationship x
                   WHERE x.workspace_id = %(ws)s AND x.name = %(name)s
                     AND x.source_entity_id = e1.source_entity_id
                     AND x.target_entity_id = e2.target_entity_id)
ON CONFLICT DO NOTHING
