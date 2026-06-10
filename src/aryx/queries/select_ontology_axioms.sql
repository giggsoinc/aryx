SELECT id, subject_type, kind, payload
FROM aryx_ontology_axiom
WHERE workspace_id = %s
ORDER BY subject_type, kind, id
