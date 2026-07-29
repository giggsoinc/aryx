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

export interface GraphEntityNode { id: number; type: string; name: string }
export interface GraphEntityEdge { source: number; target: number; name: string }

export interface EntityGraphView {
  nodes: GraphEntityNode[];
  edges: GraphEntityEdge[];
  entity_count: number;
  relationship_count: number;
}

export interface EntityRelationship {
  direction: "in" | "out";
  name: string;
  other_id: number;
  other_name: string;
  other_type: string;
}

export interface EntityDetail {
  id: number;
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

// ── User Intent Capture (C01) ──────────────────────────────────────────
export interface IntentDateRange {
  start: string;
  end: string;
}

export interface IntentPreferences {
  preferred_kpis: string[];
  preferred_dimensions: string[];
  preferred_chart_types: string[];
  target_audience: string;
  date_range: IntentDateRange | null;
}

export interface UserIntentRequest {
  uploaded_file: string;
  domain: string;
  objective: string;
  preferred_kpis: string[];
  preferred_dimensions: string[];
  preferred_chart_types: string[];
  target_audience: string;
  date_range?: IntentDateRange | null;
  request_id?: string;
}

export interface UserIntent {
  request_id: string;
  schema_version: string;
  uploaded_file: string;
  domain: string;
  objective: string;
  preferences: IntentPreferences;
  validation_status: "valid" | "invalid";
  warnings: string[];
  errors: string[];
  created_at: string;
}

// ── Knowledge Graph Intake & Validation (C05) ──────────────────────────
export interface ValidationIssue {
  code: string;
  detail: string;
  count: number;
}

export interface GraphIntakeResult {
  graph_id: string;
  graph_version: string;
  schema_version: string;
  dataset_ids: string[];
  content_hash: string;
  normalized_graph_ref: string;
  entity_count: number;
  relationship_count: number;
  duplicate_entities: number;
  duplicate_relationships: number;
  dangling_relationships: number;
  empty_collections: string[];
  schema_status: "valid" | "invalid";
  issues: ValidationIssue[];
  created_at: string;
}

// ── Context and Resource Retrieval (C07) ───────────────────────────────
export interface ApprovedColumn {
  name: string;
  type: string;
}

export interface ResourceCitation {
  resource_id: string;
  resource_type: string;
  version: string;
  rank: number;
  retrieval_score: number;
}

export interface DatasetColumns {
  dataset_id: string;
  dataset_version: string;
  approved_columns: ApprovedColumn[];
}

export interface PlanningContext {
  planning_context_id: string;
  dataset_id: string;
  dataset_version: string;
  schema_version: string;
  domain: string;
  objective: string;
  approved_columns: ApprovedColumn[];
  /** Non-empty only for the workspace-wide context — columns grouped per
   *  source dataset (never flattened; see backend docstring for why). */
  datasets: DatasetColumns[];
  approved_graph_paths: string[];
  supported_operations: string[];
  supported_charts: string[];
  resource_citations: ResourceCitation[];
  completeness: Record<string, unknown>;
  relevance: Record<string, unknown>;
  warnings: string[];
  context_status: "complete" | "incomplete" | "blocked";
  created_at: string;
}

// ── Andie Jr Planning Orchestrator (C08) ───────────────────────────────
export interface BusinessQuestion {
  question_id: string;
  text: string;
}

export interface KpiFilter {
  column: string;
  operator: string;
  value: unknown;
  values: unknown[] | null;
}

export interface KpiOperand {
  operation: string;
  filter: KpiFilter | null;
}

export interface Kpi {
  kpi_id: string;
  name: string;
  /** Which dataset this KPI's columns come from (workspace-scope only; "" in single-dataset mode). */
  dataset_id: string;
  source_columns: string[];
  operation: string;
  measure: string | null;
  filter: KpiFilter | null;
  numerator: KpiOperand | null;
  denominator: KpiOperand | null;
  zero_denominator_policy: string | null;
  format: string;
}

export interface Analysis {
  analysis_id: string;
  operation: string;
  /** Which dataset this analysis's columns come from (workspace-scope only). */
  dataset_id: string;
  group_by: string[];
  metric: string | null;
  sort: string | null;
}

export interface Visualization {
  chart_id: string;
  chart_type: string;
  source_ref: string;
  x_axis: string | null;
  y_axis: string | null;
}

export interface Assumption {
  code: string;
  meaning: string;
}

export interface SpecWarning {
  code: string;
  column: string;
  detail: string;
}

export interface DashboardSpec {
  spec_id: string;
  dataset_id: string;
  dataset_version: string;
  schema_version: string;
  output_schema_version: string;
  objective: string;
  target_audience: string;
  business_questions: BusinessQuestion[];
  kpis: Kpi[];
  analyses: Analysis[];
  visualizations: Visualization[];
  assumptions: Assumption[];
  warnings: SpecWarning[];
  spec_status: "valid" | "invalid";
  model_name: string;
  model_tier: string;
  prompt_version: string;
  created_at: string;
}

export interface SpecCheckResult {
  check: string;
  status: "passed" | "failed";
}

export interface SpecValidationError {
  code: string;
  path: string;
  reference: string;
}

export interface SpecValidationWarning {
  code: string;
  scope: string;
}

export interface SpecRetryInfo {
  allowed: boolean;
  remaining_attempts: number;
  target: string;
}

/** C09 — Pre-Execution Specification Validation. Internal to C08's run flow
 *  (no panel of its own) — attached to a PlannerResult for audit/display. */
export interface SpecValidationReport {
  validation_id: string;
  stage: "pre_execution";
  status: "approved" | "rejected";
  checks: SpecCheckResult[];
  warnings: SpecValidationWarning[];
  errors: SpecValidationError[];
  eligible_for_compilation: boolean;
  retry: SpecRetryInfo | null;
  attempt: number;
  created_at: string;
}

export interface TransformationEntry {
  column: string;
  operation: string;
  failed_rows: number;
  changed_rows: number;
  reverted: boolean;
}

/** C10 — Preprocessing and Transformation. Chained onto C09's approval, no
 *  trigger of its own. Metadata/log only — not a copy of the transformed
 *  row data (see docs/C01-C08_status.md's C10 section). */
export interface AnalysisDataset {
  analysis_dataset_id: string;
  source_dataset_id: string;
  source_dataset_version: string;
  row_count: number;
  transformations: TransformationEntry[];
  quality_summary: Record<string, number>;
  lineage_map_ref: string;
  status: "ready" | "ready_with_warnings";
  created_at: string;
}

export interface PlannerResult {
  status: "valid" | "invalid" | "controlled_error" | "controlled_failure";
  spec: DashboardSpec | null;
  error_code: string | null;
  error_message: string;
  attempts: number;
  validation: SpecValidationReport | null;
  analysis_datasets: AnalysisDataset[];
  created_at: string;
}

// ── Knowledge Graph Profiler (C06) ─────────────────────────────────────
export interface TypeCount {
  type: string;
  count: number;
}

export interface SchemaEdge {
  source_type: string;
  relationship: string;
  target_type: string;
  count: number;
}

export interface VerifiedPath {
  path_id: string;
  path: string[];
  depth: number;
}

export interface GraphQualityFlag {
  code: string;
  detail: string;
  type: string;
  count: number;
}

export interface GraphProfile {
  graph_profile_id: string;
  graph_id: string;
  graph_version: string;
  schema_version: string;
  user_objective: string;
  maximum_path_depth: number;
  entity_count: number;
  relationship_count: number;
  entity_types: TypeCount[];
  relationship_types: TypeCount[];
  schema_edges: SchemaEdge[];
  verified_paths: VerifiedPath[];
  quality_flags: GraphQualityFlag[];
  limitations: string[];
  profile_status: "valid" | "invalid";
  created_at: string;
}

// ── Semantic Field Interpreter (C04) ───────────────────────────────────
export interface AlternativeMapping {
  business_concept: string;
  confidence: number;
}

export interface SemanticAnnotation {
  column: string;
  business_concept: string;
  confidence: number;
  ontology_type: string;
  ontology_attribute: string;
  evidence: string;
  alternatives: AlternativeMapping[];
}

export interface UnresolvedField {
  column: string;
  reason: string;
  best_confidence: number;
}

export interface SemanticProfile {
  semantic_profile_id: string;
  dataset_id: string;
  dataset_version: string;
  dataset_profile_ref: string;
  domain: string;
  schema_version: string;
  annotations: SemanticAnnotation[];
  unresolved_fields: UnresolvedField[];
  warnings: string[];
  profile_status: "valid" | "invalid";
  created_at: string;
}

// ── Deterministic Dataset Profiler (C03) ───────────────────────────────
export interface ColumnProfile {
  name: string;
  original_type: string;
  canonical_type: string;
  null_count: number;
  unique_count: number;
  sample_values: string[];
  candidate_role: string;
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
  top_categories: { value: string; count: number }[];
}

export interface QualityFlag {
  column: string;
  code: string;
  count: number;
  detail: string;
}

export interface DatasetProfile {
  dataset_profile_id: string;
  dataset_id: string;
  dataset_version: string;
  schema_version: string;
  row_count: number;
  column_count: number;
  duplicate_row_count: number;
  empty_row_count: number;
  columns: ColumnProfile[];
  quality_flags: QualityFlag[];
  limitations: string[];
  profile_status: "valid" | "invalid";
  created_at: string;
}

// ── Dataset Upload & Ingestion (C02) ───────────────────────────────────
export interface DatasetIngestResult {
  request_id: string;
  dataset_id: string;
  dataset_version: string;
  schema_version: string;
  format: string;
  content_hash: string;
  raw_snapshot_ref: string;
  row_count_estimate: number;
  columns: string[];
  sheets: string[];
  ingestion_status: "accepted" | "rejected" | "duplicate";
  processing_status: string;
  errors: string[];
  file_name: string;
  file_size_bytes: number;
  created_at: string;
}
