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

export interface AskResponse {
  answer: string;
  terms: string[];
  tools_called: unknown[];
  usage: Usage;
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
