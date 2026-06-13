WITH RECURSIVE chain AS (
    SELECT name, parent_type, 0 AS depth
    FROM aryx_ontology_type
    WHERE workspace_id = %s AND name = %s
    UNION ALL
    SELECT t.name, t.parent_type, c.depth + 1
    FROM aryx_ontology_type t
    JOIN chain c ON t.name = c.parent_type
    WHERE t.workspace_id = %s AND c.depth < 16
)
SELECT name, depth
FROM chain
WHERE depth > 0
ORDER BY depth
