INSERT INTO aryx_entity (workspace_id, ontology_type, attributes, confidence)
VALUES (%s, %s, %s, %s)
RETURNING id
