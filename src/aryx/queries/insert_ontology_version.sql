INSERT INTO aryx_ontology_version (
    workspace_id, version_no, label, types_json, rules_json, created_by
)
VALUES (
    %s,
    COALESCE((SELECT MAX(version_no) + 1 FROM aryx_ontology_version
              WHERE workspace_id = %s), 1),
    %s, %s, %s, %s
)
RETURNING id, version_no, created_at
