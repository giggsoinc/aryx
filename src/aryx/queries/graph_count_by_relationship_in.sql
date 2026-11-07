-- (source)<-[rel]-(target): the edge runs target -> source.
SELECT aryx_display_name(t.attributes, t.id) AS name, count(*) AS n
FROM (SELECT source_entity_id, target_entity_id
        FROM aryx_relationship
       WHERE workspace_id = %(ws)s AND name = %(rel)s
      UNION
      SELECT source_entity_id, target_entity_id
        FROM aryx_inferred_relationship
       WHERE workspace_id = %(ws)s AND name = %(rel)s) r
JOIN aryx_entity s ON s.workspace_id = %(ws)s AND s.id = r.target_entity_id
                  AND s.ontology_type = %(source_type)s
JOIN aryx_entity t ON t.workspace_id = %(ws)s AND t.id = r.source_entity_id
                  AND t.ontology_type = %(target_type)s
GROUP BY 1
