-- Exact entity count per ontology type for one workspace. No row cap: the Ask
-- overview used to count the first 500 entities and report that as the total.
SELECT ontology_type, count(*) AS n
FROM aryx_entity
WHERE workspace_id = %(ws)s
GROUP BY ontology_type
ORDER BY ontology_type
