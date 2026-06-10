INSERT INTO aryx_ontology_axiom (workspace_id, subject_type, kind, payload, payload_hash)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, subject_type, kind, payload_hash) DO NOTHING
RETURNING id
