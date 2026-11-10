SELECT entity_id, label
FROM aryx_inferred_label
WHERE workspace_id = %(ws)s AND entity_id = ANY(%(ids)s)
