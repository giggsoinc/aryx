-- Same, against edge direction (walks target -> source).
SELECT r.target_entity_id AS frm, r.source_entity_id AS tov,
       (array_agg(r.name ORDER BY r.src, r.id))[1] AS rel
FROM (
  SELECT source_entity_id, target_entity_id, name, id, 0 AS src
    FROM aryx_relationship
   WHERE workspace_id = %(ws)s AND target_entity_id = ANY(%(frontier)s)
  UNION ALL
  SELECT source_entity_id, target_entity_id, name, 0 AS id, 1 AS src
    FROM aryx_inferred_relationship
   WHERE workspace_id = %(ws)s AND target_entity_id = ANY(%(frontier)s)
) r
JOIN aryx_entity t ON t.workspace_id = %(ws)s AND t.id = r.source_entity_id
GROUP BY r.target_entity_id, r.source_entity_id
ORDER BY 1, 2
