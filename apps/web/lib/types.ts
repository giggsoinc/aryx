// Wire types — these mirror the FastAPI JSON contract, hand-written for V1.
// Later: regenerate from /openapi.json at build time. They live HERE (in the
// frontend) and never get imported back into Python — backend stays oblivious.

export interface Citation {
  /** Entity id grounding a claim in the answer. */
  entity_id: number;
  /** Display label (entity name). */
  label: string;
  /** Optional entity type (Customer, Ticket, etc.) */
  type?: string;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  menial_model?: string;
  answer_model?: string;
}

/** Live LLM runtime config (GET /llm/config · POST /admin/llm/config). */
export interface LlmConfig {
  provider: string;
  menial_model: string;
  answer_model: string;
  endpoint: string;
  api_key_set: boolean;
}

export interface LlmConfigUpdate {
  provider?: string;
  menial_model?: string;
  answer_model?: string;
  endpoint?: string;
  api_key?: string;
}

export interface AskResponse {
  answer: string;
  terms: string[];
  tools_called: unknown[];
  usage: Usage;
  grounding?: Grounding | null;
}

// ── Accuracy Lab (v2) ───────────────────────────────────────────────────
export interface GroundingCitation {
  marker: number;
  entity_id: number;
  entity_name: string;
  entity_type: string;
  system: string;
  dataset: string;
  record_id: string;
}

export interface Grounding {
  grounded: boolean;
  entity_count: number;
  cited_count: number;
  source_count: number;
  score: number;
  citations: GroundingCitation[];
  uncited_entities: string[];
}

export interface AbVariant {
  label: string;
  grounded_in_ontology: boolean;
  answer: string;
  grounding: Grounding;
}

export interface AbScorecard {
  grounded: { on: boolean; off: boolean };
  citations: { on: number; off: number };
  source_records: { on: number; off: number };
  evidence_used: { on: number; off: number };
}

export interface AbResult {
  question: string;
  model: string;
  on: AbVariant;
  off: AbVariant;
  scorecard: AbScorecard;
}

export interface ReasonerCheck {
  axioms_checked: number;
  entities_scanned: number;
  violations: number;
  blocked: number;
}

// ── Data Explorer (v2) ──────────────────────────────────────────────────
export interface DataTypeCount { name: string; count: number }
export interface DataSourceCount { source: string; count: number }

export interface DataSummary {
  total_entities: number;
  type_count: number;
  types: DataTypeCount[];
  sources: DataSourceCount[];
  source_records: number;
  duplicates_merged: number;
}

export interface ProvenanceRef {
  system: string;
  dataset: string;
  record_id: string;
}

export interface DataEntity {
  id: number;
  type: string;
  name: string;
  attributes: Record<string, unknown>;
  sources: ProvenanceRef[];
}

export interface DataEntitiesPage {
  type: string | null;
  total: number;
  offset: number;
  limit: number;
  items: DataEntity[];
}

export interface DataEntityGroup {
  key: string;
  count: number;
  items: DataEntity[];
}

export interface DataEntitiesGrouped {
  grouped: true;
  group_attr: string;
  label_attr: string | null;
  total_groups: number;
  group_offset: number;
  group_limit: number;
  groups: DataEntityGroup[];
}

export interface GraphTypeNode { type: string; count: number }
export interface GraphTypeEdge {
  source: string;
  target: string;
  name: string;
  count: number;
}

export interface GraphView {
  type_nodes: GraphTypeNode[];
  type_edges: GraphTypeEdge[];
  entity_count: number;
  relationship_count: number;
}

export interface GraphEntityNode { id: number | string; type: string; name: string }
export interface GraphEntityEdge {
  source: number | string;
  target: number | string;
  name: string;
}

export interface EntityGraphView {
  nodes: GraphEntityNode[];
  edges: GraphEntityEdge[];
  entity_count: number;
  relationship_count: number;
}

export interface EntityRelationship {
  direction: "in" | "out";
  name: string;
  other_id: number | string;
  other_name: string;
  other_type: string;
}

export interface EntityDetail {
  id: number | string;
  type: string;
  name: string;
  attributes: Record<string, unknown>;
  sources: { system: string; dataset: string; record_id: string }[];
  relationships: EntityRelationship[];
}

export interface Workspace {
  id: number;
  name: string;
  description?: string;
  context?: string;
  brief?: Record<string, unknown>;
}

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  usage?: Usage;
  streaming?: boolean;
}

// ─── Ontology / modelling layer ───────────────────────────────────────────

export interface OntologyType {
  name: string;
  attributes: string[];
  status?: "proposed" | "approved" | string;
  source?: string;
  parent_type?: string | null;
  instance_count?: number;
}

export interface OntologyRelationship {
  /** Backend row id — present only for declared relationship types
   *  (W2 / aryx_relationship_type). Subclass + entity-derived edges have none. */
  id?: number;
  name: string;
  source_type?: string;
  target_type?: string;
  count?: number;
}

export interface OntologyDoc {
  types: OntologyType[];
  relationships: OntologyRelationship[];
  entity_count?: number;
}

export interface Axiom {
  id: number;
  kind: string;
  type_name: string;
  payload: Record<string, unknown>;
}

export interface Rule {
  name: string;
  when_type: string;
  attribute: string;
  operator: string;
  value: string;
  action: string;
  label?: string;
  target_type?: string;
  target_name?: string;
  enabled: boolean;
}

export interface SurvivorshipPolicy {
  default_strategy?: string;
  attribute_strategies?: Record<string, string>;
  source_priority?: string[];
}

export interface IngestQuestion {
  id: number;
  workspace_id: number;
  job_id?: string;
  kind: string;
  prompt: string;
  options?: string[];
  suggested?: string;
  status: "pending" | "answered" | string;
  answer?: string;
  type_name?: string;
}

export interface Brief {
  domain?: string;
  aim?: string;
  objectives?: string[];
  scope?: string;
  roles?: string[];
}

export interface QuizField {
  name: string;
  label: string;
  required?: boolean;
  secret?: boolean;
  help?: string;
  default?: string;
  options?: string[];
  kind?: string;
}

export interface QuizSpec {
  kind: string;
  label: string;
  fields: QuizField[];
}

export interface Datasource {
  id: number;
  workspace_id: number;
  name: string;
  kind: string;
  config: Record<string, unknown>;
  mask: string;
  ready: boolean;
}
