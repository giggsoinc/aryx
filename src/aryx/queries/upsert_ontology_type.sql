INSERT INTO aryx_ontology_type (name, attributes, status, source)
VALUES (%s, %s, %s, %s)
ON CONFLICT (name) DO NOTHING
