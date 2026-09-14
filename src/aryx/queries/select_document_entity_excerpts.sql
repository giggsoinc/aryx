SELECT span FROM (
    SELECT DISTINCT ON (l.payload->>'span') l.payload->>'span' AS span
    FROM aryx_entity_member m
    JOIN aryx_landed_record l
      ON l.id = m.landed_record_id AND l.workspace_id = m.workspace_id
    JOIN aryx_entity e
      ON e.id = m.entity_id AND e.workspace_id = m.workspace_id
    WHERE m.workspace_id = %s
      AND l.source_system = 'document'
      AND e.ontology_type = %s
      AND e.attributes->>'name' = %s
      AND l.payload->>'span' IS NOT NULL
    ORDER BY l.payload->>'span'
) deduped
ORDER BY length(span) DESC
LIMIT %s
