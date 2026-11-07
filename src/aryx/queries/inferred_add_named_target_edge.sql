-- add_relationship rule: connect one source entity to every entity of the
-- given type whose display name matches. Returns the rows it created.
INSERT INTO aryx_inferred_relationship
    (workspace_id, source_entity_id, target_entity_id, name, rule_name)
SELECT %(ws)s, %(source)s, t.id, %(name)s, %(rule)s
FROM aryx_entity t
WHERE t.workspace_id = %(ws)s
  AND t.ontology_type = %(target_type)s
  AND aryx_display_name(t.attributes, t.id) = %(target_name)s
  AND EXISTS (SELECT 1 FROM aryx_entity s
               WHERE s.workspace_id = %(ws)s AND s.id = %(source)s)
ON CONFLICT DO NOTHING
