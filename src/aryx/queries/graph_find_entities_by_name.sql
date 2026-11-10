-- Case-insensitive substring on the display name. LIKE (not strpos) so the
-- pg_trgm index on lower(aryx_display_name(..)) can serve it; the caller's
-- text is escaped so percent, underscore and backslash match literally.
SELECT e.id, e.ontology_type, aryx_display_name(e.attributes, e.id) AS name
FROM aryx_entity e
WHERE e.workspace_id = %(ws)s
  AND lower(aryx_display_name(e.attributes, e.id))
      LIKE '%%' || replace(replace(replace(lower(%(name)s), '\', '\\'), '%%', '\%%'), '_', '\_') || '%%'
ORDER BY e.id
LIMIT %(limit)s
