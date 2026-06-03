SELECT id, workspace_id, actor, op, target_kind, target_name,
       before_json, after_json, changed_at
FROM aryx_ontology_change_log
WHERE workspace_id = %s
ORDER BY changed_at DESC
LIMIT %s
