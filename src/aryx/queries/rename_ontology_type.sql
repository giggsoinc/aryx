UPDATE aryx_ontology_type SET name = %s
WHERE workspace_id = %s AND name = %s
RETURNING id
