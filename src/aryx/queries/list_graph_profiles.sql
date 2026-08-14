SELECT profile FROM aryx_graph_profile
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
