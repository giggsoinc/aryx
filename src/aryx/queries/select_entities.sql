SELECT id, ontology_type, attributes
FROM aryx_entity
WHERE workspace_id = %s
