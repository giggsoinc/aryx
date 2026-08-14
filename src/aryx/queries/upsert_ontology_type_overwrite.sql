INSERT INTO aryx_ontology_type (workspace_id, name, attributes, status, source)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, name) DO UPDATE SET
    attributes = EXCLUDED.attributes,
    status = EXCLUDED.status,
    source = EXCLUDED.source
