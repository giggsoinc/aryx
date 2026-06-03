UPDATE aryx_ontology_rule
SET enabled = %s
WHERE workspace_id = %s AND name = %s
RETURNING id, name, enabled
