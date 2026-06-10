-- Aryx ontology axioms (Night 2, Phases 2 & 4).
-- Workspace-scoped formal-ontology constraints over types and properties.
-- Kinds emitted to OWL on export:
--   disjoint_with      -> owl:disjointWith   (payload: {"object_type": "..."})
--   equivalent_to      -> owl:equivalentClass(payload: {"object_type": "..."})
--   domain             -> rdfs:domain        (payload: {"property": "..."})
--   range              -> rdfs:range         (payload: {"property": "...",
--                                                       "datatype": "xsd:string"
--                                                       | "class": "TypeName"})
--   cardinality_max    -> owl:maxCardinality (payload: {"property": "...",
--                                                       "max": 1})
-- payload_hash gives deterministic idempotency without a giant UNIQUE on JSONB.

CREATE TABLE IF NOT EXISTS aryx_ontology_axiom (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL,
    subject_type  TEXT   NOT NULL,
    kind          TEXT   NOT NULL,
    payload       JSONB  NOT NULL DEFAULT '{}'::jsonb,
    payload_hash  TEXT   NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, subject_type, kind, payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_axiom_ws_subject
    ON aryx_ontology_axiom (workspace_id, subject_type);

CREATE INDEX IF NOT EXISTS idx_axiom_ws_kind
    ON aryx_ontology_axiom (workspace_id, kind);

CREATE TABLE IF NOT EXISTS aryx_axiom_violation (
    id            BIGSERIAL PRIMARY KEY,
    workspace_id  BIGINT NOT NULL,
    entity_id     BIGINT NOT NULL,
    axiom_id      BIGINT NOT NULL REFERENCES aryx_ontology_axiom (id) ON DELETE CASCADE,
    reason        TEXT   NOT NULL,
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_violation_ws_entity
    ON aryx_axiom_violation (workspace_id, entity_id);
