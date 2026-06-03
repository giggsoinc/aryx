DELETE FROM aryx_ontology_rule
WHERE workspace_id = %s AND name = %s
RETURNING id
