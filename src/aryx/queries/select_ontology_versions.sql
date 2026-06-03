SELECT id, workspace_id, version_no, label, types_json, rules_json,
       created_by, created_at
FROM aryx_ontology_version
WHERE workspace_id = %s
ORDER BY version_no DESC
LIMIT %s
