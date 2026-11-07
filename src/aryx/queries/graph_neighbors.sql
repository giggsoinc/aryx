-- One hop in both directions, asserted and inferred. Edges are de-duplicated
-- (the FalkorDB MERGE did that) and both endpoints must exist (FalkorDB
-- skipped dangling edges). The last column flags reasoning-engine edges.
WITH edges AS (
  SELECT r.target_entity_id AS other, r.name AS rel, 'out' AS dir, false AS inferred
    FROM aryx_relationship r
   WHERE r.workspace_id = %(ws)s AND r.source_entity_id = %(id)s
  UNION
  SELECT r.source_entity_id, r.name, 'in', false
    FROM aryx_relationship r
   WHERE r.workspace_id = %(ws)s AND r.target_entity_id = %(id)s
  UNION
  SELECT i.target_entity_id, i.name, 'out', true
    FROM aryx_inferred_relationship i
   WHERE i.workspace_id = %(ws)s AND i.source_entity_id = %(id)s
  UNION
  SELECT i.source_entity_id, i.name, 'in', true
    FROM aryx_inferred_relationship i
   WHERE i.workspace_id = %(ws)s AND i.target_entity_id = %(id)s
)
SELECT n.id, n.ontology_type, aryx_display_name(n.attributes, n.id) AS name,
       e.rel, e.dir, e.inferred
FROM edges e
JOIN aryx_entity n ON n.workspace_id = %(ws)s AND n.id = e.other
WHERE EXISTS (SELECT 1 FROM aryx_entity me
               WHERE me.workspace_id = %(ws)s AND me.id = %(id)s)
ORDER BY e.rel, e.dir, n.id, e.inferred
