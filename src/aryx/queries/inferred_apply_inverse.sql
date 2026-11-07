-- A -[fwd]-> B  =>  B -[inv]-> A, over asserted edges only. Pairs that already
-- exist as an asserted edge are skipped, so an asserted edge is never
-- relabelled as inferred. Safe to re-run: the primary key absorbs repeats.
INSERT INTO aryx_inferred_relationship
    (workspace_id, source_entity_id, target_entity_id, name, rule_name)
SELECT DISTINCT %(ws)s, r.target_entity_id, r.source_entity_id, %(inv)s, %(rule)s
FROM aryx_relationship r
JOIN aryx_entity s ON s.workspace_id = %(ws)s AND s.id = r.source_entity_id
JOIN aryx_entity t ON t.workspace_id = %(ws)s AND t.id = r.target_entity_id
WHERE r.workspace_id = %(ws)s AND r.name = %(fwd)s
  AND NOT EXISTS (SELECT 1 FROM aryx_relationship x
                   WHERE x.workspace_id = %(ws)s AND x.name = %(inv)s
                     AND x.source_entity_id = r.target_entity_id
                     AND x.target_entity_id = r.source_entity_id)
ON CONFLICT DO NOTHING
