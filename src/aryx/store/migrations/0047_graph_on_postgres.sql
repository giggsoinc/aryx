-- Graph served from Postgres (replaces the FalkorDB projection).
-- Additive and idempotent: apply_migrations re-runs every file on every call.
-- Never edit this file once released; add a new migration instead.

-- Port of falkor_store._display_name: first truthy value of a fixed key list,
-- else the first string value of 1-80 characters in stored key order, else
-- '#<id>'. Python truthiness: "", 0, false, null, [] and {} are skipped.
-- Known deviation: a NON-EMPTY array/object value renders as its JSON text,
-- not Python's repr() (single quotes, True/False). Real data never names an
-- entity with a container; documented, not replicated.
CREATE OR REPLACE FUNCTION aryx_display_name(attrs jsonb, entity_id bigint)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $fn$
SELECT COALESCE(
  (SELECT t.txt
     FROM unnest(ARRAY['name', 'full_name', 'title', 'label', 'ticket_ref',
                       'ref', 'sku', 'code', 'email', 'username'])
          WITH ORDINALITY AS kn(attr_name, ord)
     CROSS JOIN LATERAL (SELECT attrs -> kn.attr_name AS v) j
     CROSS JOIN LATERAL (
       SELECT CASE jsonb_typeof(j.v)
         WHEN 'string'  THEN NULLIF(j.v #>> '{}', '')
         WHEN 'number'  THEN CASE WHEN (j.v #>> '{}')::numeric <> 0
                                  THEN j.v #>> '{}' END
         WHEN 'boolean' THEN CASE WHEN j.v = 'true'::jsonb THEN 'True' END
         WHEN 'array'   THEN CASE WHEN jsonb_array_length(j.v) > 0
                                  THEN j.v::text END
         WHEN 'object'  THEN CASE WHEN j.v <> '{}'::jsonb THEN j.v::text END
       END AS txt
     ) t
    WHERE t.txt IS NOT NULL
    ORDER BY kn.ord
    LIMIT 1),
  (SELECT s.val #>> '{}'
     FROM jsonb_each(attrs) WITH ORDINALITY AS s(attr_name, val, ord)
    WHERE jsonb_typeof(s.val) = 'string'
      AND char_length(s.val #>> '{}') BETWEEN 1 AND 80
    ORDER BY s.ord
    LIMIT 1),
  '#' || entity_id::text
);
$fn$;

-- Substring name search (find_entities, Ask lookups) scans every row without
-- this. Phase 0 measured a no-match search at 1.8 s on 100k entities without
-- it and 0.6 ms with it. If pg_trgm is unavailable on the target Postgres the
-- two statements are skipped (apply_migrations logs and continues) and search
-- still works, only slower.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_entity_name_trgm
    ON aryx_entity USING gin (lower(aryx_display_name(attributes, id)) gin_trgm_ops);

-- count_by_relationship filters on (workspace_id, name).
CREATE INDEX IF NOT EXISTS idx_rel_ws_name
    ON aryx_relationship (workspace_id, name);

-- Edges derived by the reasoning engine (inverse, symmetric, transitive,
-- add_relationship rules). Kept apart from aryx_relationship so asserted
-- edges are never polluted; cleared whenever the graph changes.
CREATE TABLE IF NOT EXISTS aryx_inferred_relationship (
    workspace_id     BIGINT NOT NULL,
    source_entity_id BIGINT NOT NULL,
    target_entity_id BIGINT NOT NULL,
    name             TEXT   NOT NULL,
    rule_name        TEXT   NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, source_entity_id, target_entity_id, name)
);

CREATE INDEX IF NOT EXISTS idx_inf_rel_ws_target
    ON aryx_inferred_relationship (workspace_id, target_entity_id);

-- Labels set by the set_label rule action.
CREATE TABLE IF NOT EXISTS aryx_inferred_label (
    workspace_id BIGINT NOT NULL,
    entity_id    BIGINT NOT NULL,
    label        TEXT   NOT NULL,
    rule_name    TEXT   NOT NULL DEFAULT '',
    PRIMARY KEY (workspace_id, entity_id)
);
