UPDATE aryx_ontology_rule
SET fires_count = fires_count + %s,
    last_run_at = now()
WHERE workspace_id = %s AND name = %s
