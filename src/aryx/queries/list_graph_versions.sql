SELECT report FROM aryx_graph_version
WHERE workspace_id = %s
ORDER BY created_at DESC
LIMIT %s
