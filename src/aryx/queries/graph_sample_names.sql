-- The first %(n)s display names of EVERY ontology type in ONE query (the Ask
-- overview used to issue one find_entities query per type). Each type is read
-- through the (workspace_id, ontology_type) index, in id order.
SELECT t.ontology_type, s.name
FROM (SELECT DISTINCT ontology_type
        FROM aryx_entity
       WHERE workspace_id = %(ws)s) t
CROSS JOIN LATERAL (
  SELECT e.id, aryx_display_name(e.attributes, e.id) AS name
    FROM aryx_entity e
   WHERE e.workspace_id = %(ws)s AND e.ontology_type = t.ontology_type
   ORDER BY e.id
   LIMIT %(n)s
) s
ORDER BY t.ontology_type, s.id
