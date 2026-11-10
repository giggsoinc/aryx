SELECT DISTINCT l.source_system, l.source_dataset, l.source_record_id
FROM aryx_entity_member m
JOIN aryx_landed_record l
  ON l.id = m.landed_record_id AND l.workspace_id = m.workspace_id
WHERE m.workspace_id = %(ws)s AND m.entity_id = %(id)s
  AND EXISTS (SELECT 1 FROM aryx_entity e
               WHERE e.workspace_id = %(ws)s AND e.id = %(id)s)
ORDER BY 1, 2, 3
