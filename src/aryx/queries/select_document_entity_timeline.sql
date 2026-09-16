SELECT (e.created_at AT TIME ZONE 'UTC')::date AS entity_date, COUNT(DISTINCT e.id) AS entity_count
FROM aryx_entity e
JOIN aryx_entity_member m
  ON m.entity_id = e.id AND m.workspace_id = e.workspace_id
JOIN aryx_landed_record l
  ON l.id = m.landed_record_id AND l.workspace_id = m.workspace_id
WHERE e.workspace_id = %s
  AND l.source_system = 'document'
GROUP BY entity_date
ORDER BY entity_date
