SELECT id, ontology_type, aryx_display_name(attributes, id) AS name
FROM aryx_entity
WHERE workspace_id = %(ws)s AND ontology_type = %(type)s
ORDER BY id
LIMIT %(limit)s
