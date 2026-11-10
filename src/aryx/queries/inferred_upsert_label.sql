INSERT INTO aryx_inferred_label (workspace_id, entity_id, label, rule_name)
VALUES (%(ws)s, %(entity)s, %(label)s, %(rule)s)
ON CONFLICT (workspace_id, entity_id)
DO UPDATE SET label = EXCLUDED.label, rule_name = EXCLUDED.rule_name
