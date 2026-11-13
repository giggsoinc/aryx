-- Value counts for the low-cardinality attributes of every ontology type, e.g.
-- Ticket.status -> open 26 / closed 54. This is what lets Ask answer "how many
-- tickets are open?" exactly instead of guessing.
--
-- A key qualifies when it has at most %(max_values)s distinct values AND fewer
-- distinct values than records of that type. The second test drops identifiers
-- and names (every value unique) so only real categories remain. Only scalar
-- attributes up to 40 characters are considered.
WITH kv AS (
  SELECT e.ontology_type AS t, a.key AS k, a.value AS v
  FROM aryx_entity e
  CROSS JOIN LATERAL jsonb_each_text(
       CASE WHEN jsonb_typeof(e.attributes) = 'object'
            THEN e.attributes ELSE '{}'::jsonb END) a
  WHERE e.workspace_id = %(ws)s
    AND jsonb_typeof(e.attributes -> a.key) IN ('string', 'number', 'boolean')
    AND char_length(a.value) BETWEEN 1 AND 40
),
cnt AS (
  SELECT t, k, v, count(*) AS n FROM kv GROUP BY t, k, v
),
card AS (
  SELECT t, k, count(*) AS distinct_values FROM cnt GROUP BY t, k
),
total AS (
  SELECT ontology_type AS t, count(*) AS records
  FROM aryx_entity
  WHERE workspace_id = %(ws)s
  GROUP BY ontology_type
)
SELECT cnt.t, cnt.k, cnt.v, cnt.n
FROM cnt
JOIN card  ON card.t = cnt.t AND card.k = cnt.k
JOIN total ON total.t = cnt.t
WHERE card.distinct_values <= %(max_values)s
  AND card.distinct_values < total.records
ORDER BY cnt.t, cnt.k, cnt.n DESC, cnt.v
