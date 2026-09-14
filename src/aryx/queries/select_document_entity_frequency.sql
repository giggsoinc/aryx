SELECT e.ontology_type, e.attributes->>'name' AS entity_name, COUNT(*) AS mention_count
FROM aryx_entity_member m
JOIN aryx_landed_record l
  ON l.id = m.landed_record_id AND l.workspace_id = m.workspace_id
JOIN aryx_entity e
  ON e.id = m.entity_id AND e.workspace_id = m.workspace_id
WHERE m.workspace_id = %s
  AND l.source_system = 'document'
  AND e.attributes->>'name' IS NOT NULL
GROUP BY e.ontology_type, e.attributes->>'name'
HAVING COUNT(*) >= %s
ORDER BY mention_count DESC
LIMIT %s
