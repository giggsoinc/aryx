UPDATE aryx_action_execution
SET status = %s, applied_at = now(), effect_log = %s
WHERE id = %s
