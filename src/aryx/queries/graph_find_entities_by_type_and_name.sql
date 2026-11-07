SELECT e.id, e.ontology_type, aryx_display_name(e.attributes, e.id) AS name
FROM aryx_entity e
WHERE e.workspace_id = %(ws)s
  AND e.ontology_type = %(type)s
  AND lower(aryx_display_name(e.attributes, e.id))
      LIKE '%%' || replace(replace(replace(lower(%(name)s), '\', '\\'), '%%', '\%%'), '_', '\_') || '%%'
ORDER BY e.id
LIMIT %(limit)s
