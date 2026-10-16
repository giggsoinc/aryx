SELECT DISTINCT ON (rs.detail->>'ontology_type')
       rs.detail->>'ontology_type' AS ontology_type,
       rs.detail->'match_keys'    AS match_keys
FROM aryx_run_stage rs
JOIN aryx_run r ON r.run_id = rs.run_id
WHERE r.workspace_id = %s
  AND rs.detail ? 'ontology_type'
  AND rs.detail ? 'match_keys'
ORDER BY rs.detail->>'ontology_type', r.run_id DESC
