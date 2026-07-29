SELECT context FROM aryx_planning_context
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
