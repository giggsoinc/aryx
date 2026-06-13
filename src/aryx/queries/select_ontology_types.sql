SELECT name, attributes, status, source, parent_type
FROM aryx_ontology_type
WHERE workspace_id = %s
ORDER BY name
