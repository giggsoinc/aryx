-- A -[name]-> B (A != B)  =>  B -[name]-> A, over asserted edges only.
INSERT INTO aryx_inferred_relationship
    (workspace_id, source_entity_id, target_entity_id, name, rule_name)
SELECT DISTINCT %(ws)s, r.target_entity_id, r.source_entity_id, %(name)s, %(rule)s
FROM aryx_relationship r
JOIN aryx_entity s ON s.workspace_id = %(ws)s AND s.id = r.source_entity_id
JOIN aryx_entity t ON t.workspace_id = %(ws)s AND t.id = r.target_entity_id
WHERE r.workspace_id = %(ws)s AND r.name = %(name)s
  AND r.source_entity_id <> r.target_entity_id
  AND NOT EXISTS (SELECT 1 FROM aryx_relationship x
                   WHERE x.workspace_id = %(ws)s AND x.name = %(name)s
                     AND x.source_entity_id = r.target_entity_id
                     AND x.target_entity_id = r.source_entity_id)
ON CONFLICT DO NOTHING
