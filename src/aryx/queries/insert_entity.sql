INSERT INTO aryx_entity (ontology_type, attributes, confidence)
VALUES (%s, %s, %s)
RETURNING id
