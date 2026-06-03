INSERT INTO aryx_ontology_rule (
    workspace_id, name, when_clause, then_clause, enabled
)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (workspace_id, name) DO UPDATE
SET when_clause = EXCLUDED.when_clause,
    then_clause = EXCLUDED.then_clause,
    enabled     = EXCLUDED.enabled
RETURNING id, name, enabled, fires_count, created_at
