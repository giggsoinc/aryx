UPDATE aryx_entity SET ontology_type = %s
WHERE workspace_id = %s AND id = %s
RETURNING id
