INSERT INTO aryx_ontology_change_log (
    workspace_id, actor, op, target_kind, target_name,
    before_json, after_json
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
RETURNING id, changed_at
