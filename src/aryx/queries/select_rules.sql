SELECT id, workspace_id, name, when_clause, then_clause, enabled,
       fires_count, last_run_at, created_at
FROM aryx_ontology_rule
WHERE workspace_id = %s
ORDER BY created_at
