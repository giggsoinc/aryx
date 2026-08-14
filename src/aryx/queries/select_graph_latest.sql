SELECT report FROM aryx_graph_version
WHERE workspace_id = %s AND graph_id = %s
ORDER BY created_at DESC
LIMIT 1
