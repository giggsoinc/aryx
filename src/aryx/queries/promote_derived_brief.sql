-- Atomically promote a derived brief, ONLY while the customer has none.
--
-- The soft-gate promote used to be read-then-write across three separate
-- autocommit statements: read brief, decide, write brief, write
-- brief_source. A customer saving their brief inside that window had it
-- silently overwritten by the model's reading — the exact invariant
-- brief-first exists to protect — and a crash between the last two left a
-- derived brief still labelled 'customer'.
--
-- The WHERE clause mirrors aryx.brief.is_populated: every scalar field
-- blank and no non-blank entry in any list field. `source_docs` is
-- deliberately excluded, exactly as is_populated excludes it — a filename
-- is provenance, not an authored brief.
--
-- Zero rows updated means someone else won the race; the caller must
-- re-read rather than assume it promoted.
UPDATE aryx_workspace
SET brief = %s, brief_source = 'derived'
WHERE id = %s
  AND btrim(COALESCE(brief ->> 'domain', '')) = ''
  AND btrim(COALESCE(brief ->> 'aim', '')) = ''
  AND btrim(COALESCE(brief ->> 'scope', '')) = ''
  AND NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
               CASE WHEN jsonb_typeof(brief -> 'objectives') = 'array'
                    THEN brief -> 'objectives' ELSE '[]'::jsonb END
             || CASE WHEN jsonb_typeof(brief -> 'roles') = 'array'
                     THEN brief -> 'roles' ELSE '[]'::jsonb END
             || CASE WHEN jsonb_typeof(brief -> 'questions') = 'array'
                     THEN brief -> 'questions' ELSE '[]'::jsonb END
             ) AS item
        WHERE btrim(item) <> ''
      )
RETURNING id, brief, brief_source
