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

/** Response from POST /pipeline/link-entities — `relationships` is the
 *  exact count of edges actually created (0 means the two attributes never
 *  matched on any real value, not a silent success). */
export interface LinkEntitiesResult {
  relationships: number;
  [key: string]: number;
}

/** Response from POST /pipeline/derive-entities — `created` is the exact
 *  count of new entities written (0 means no source entity had the
 *  group-by attribute, not a silent success). */
export interface DeriveEntitiesResult {
  type: string;
  created: number;
  source_groups: number;
  skipped_missing_key: number;
  [key: string]: number | string;
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
  /** Real example values observed in this column (from C03) — empty for
   *  non-categorical/high-cardinality columns. */
  sample_values: string[];
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
  /** row_points only (scatter/bubble): numeric columns per row. */
  x_column: string | null;
  y_column: string | null;
  size_column: string | null;
  /** date_span (gantt) / survival only. */
  start_column: string | null;
  end_column: string | null;
}

export interface Visualization {
  chart_id: string;
  chart_type: string;
  source_ref: string;
  x_axis: string | null;
  y_axis: string | null;
  /** grouped_bar/slopegraph only: a second analysis_id to compare against source_ref. */
  compare_ref?: string | null;
  /** radar only: 3+ kpi_id/analysis_id refs, one per axis. */
  axis_refs?: string[] | null;
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

export interface ExecutionNode {
  node_id: string;
  template: string;
  dataset_id: string;
  parameters: Record<string, unknown>;
  depends_on: string[];
}

export interface CompilationIssue {
  code: string;
  node_id: string;
  detail: string;
}

/** C11 — Execution Compiler. Chained onto C10's approval, no trigger of its
 *  own. Binds an approved spec's KPIs/analyses to a fixed set of vetted
 *  operation templates — no LLM, no arbitrary code generation. */
export interface ExecutionPlan {
  execution_plan_id: string;
  spec_id: string;
  dataset_id: string;
  dataset_version: string;
  nodes: ExecutionNode[];
  plan_acyclic: boolean;
  row_limit: number;
  node_limit: number;
  compilation_status: "success" | "rejected";
  issues: CompilationIssue[];
  kpi_final_node: Record<string, string>;
  kpi_lineage_nodes: Record<string, string[]>;
  analysis_node: Record<string, string>;
  created_at: string;
}

// ── Deterministic Analysis Execution (C12) ──────────────────────────────
export interface KpiLineage {
  source_columns: string[];
  operation_ids: string[];
  dataset_version: string;
}

export interface KpiResult {
  kpi_id: string;
  value: number | null;
  display_value: string;
  numerator: number | null;
  denominator: number | null;
  sample_size: number;
  excluded_null_rows: number;
  lineage: KpiLineage;
}

export interface AnalysisResultRow {
  group_value: string;
  value: number | null;
  numerator: number | null;
  denominator: number | null;
  sample_size: number;
  // Populated only for a box-plot (quartiles) row — value carries the median.
  min: number | null;
  q1: number | null;
  q3: number | null;
  max: number | null;
  // Populated only for a crosstab (sankey/treemap/sunburst/heatmap_matrix) cell.
  group_value_secondary: string | null;
  // Populated only for a row_points (scatter/bubble) point.
  x: number | null;
  y: number | null;
  size: number | null;
  // Populated only for a date_span (gantt) row — raw date strings.
  start: string | null;
  end: string | null;
  // Populated only for a survival_curve point — value carries survived_fraction,
  // sample_size carries at_risk.
  duration_days: number | null;
  // Populated only for a histogram row.
  buckets: { bucket_start: number; bucket_end: number; count: number }[] | null;
}

export interface AnalysisResult {
  analysis_id: string;
  group_column: string;
  rows: AnalysisResultRow[];
}

export interface ExecutionMetrics {
  runtime_ms: number;
  nodes_completed: number;
  nodes_failed: number;
}

/** C12 — Deterministic Analysis Execution. On-demand only (like C08) —
 *  triggered explicitly, never chained onto C08-C11's approval flow. */
// ── Post-Execution Validation (C13) ─────────────────────────────────────
export interface PostExecCheckResult {
  check: string;
  status: "passed" | "failed";
  details: Record<string, unknown>;
}

export interface PostExecWarning {
  code: string;
  reference: string;
  details: Record<string, unknown>;
}

export interface PostExecError {
  code: string;
  reference: string;
  details: Record<string, unknown>;
}

/** C13 — Post-Execution Validation. Chained onto C12, no trigger of its
 *  own. A structurally valid but numerically incorrect result is still
 *  blocked (aggregation_correctness recomputes independently). */
export interface PostExecutionReport {
  validation_id: string;
  stage: "post_execution";
  status: "approved" | "approved_with_warnings" | "rejected";
  checks: PostExecCheckResult[];
  warnings: PostExecWarning[];
  errors: PostExecError[];
  eligible_for_dashboard: boolean;
  created_at: string;
}

// ── Dashboard Composition (C14) ─────────────────────────────────────────
export interface DashboardComponent {
  component_id: string;
  type: string;
  source_ref: string;
  position: number;
  warning_refs: string[];
  // grouped_bar only: the second analysis_id to compare against source_ref.
  compare_ref: string | null;
  // radar only: carried over from Visualization.axis_refs.
  axis_refs: string[] | null;
}

export interface DashboardSection {
  section_id: string;
  title: string;
  components: DashboardComponent[];
}

export interface CompositionIssue {
  code: string;
  reference: string;
  detail: string;
}

/** C14 — Dashboard Composition. On-demand only, like C08/C12 — gated on
 *  C13's eligible_for_dashboard. Hybrid: an optional LLM step may suggest
 *  section titles, but can never add/remove/rebind a component. */
export interface DashboardModel {
  dashboard_model_id: string;
  spec_id: string;
  dataset_id: string;
  dataset_version: string;
  title: string;
  audience: string;
  sections: DashboardSection[];
  max_columns: number;
  composition_status: "valid" | "invalid";
  issues: CompositionIssue[];
  composed_by: "deterministic" | "llm_assisted";
  created_at: string;
}

// ── Frontend Dashboard Renderer (C15) — telemetry only, no compute ───────
export interface AccessibilityChecks {
  keyboard_navigation: "passed" | "failed";
  contrast: "passed" | "failed";
  text_alternatives: "passed" | "failed";
}

export interface RenderTelemetry {
  render_id: string;
  dashboard_model_id: string;
  render_status: "success" | "partial" | "failed";
  rendered_component_count: number;
  warning_count: number;
  unsupported_component_types: string[];
  accessibility_checks: AccessibilityChecks;
}

export interface ExecutionRun {
  execution_run_id: string;
  execution_plan_id: string;
  spec_id: string;
  dataset_id: string;
  dataset_version: string;
  status: "completed" | "failed" | "partial";
  kpi_results: KpiResult[];
  analysis_results: AnalysisResult[];
  execution_metrics: ExecutionMetrics;
  errors: string[];
  validation: PostExecutionReport | null;
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
  execution_plans: ExecutionPlan[];
  created_at: string;
}

// ── Ask-to-visualize (C08 extension) ────────────────────────────────────
export interface DeltaSpecItems {
  new_kpi: Kpi | null;
  new_analysis: Analysis | null;
  new_visualization: Visualization | null;
  warnings: SpecWarning[];
}

export interface DeltaDraftResult {
  status: "valid" | "invalid" | "controlled_error";
  items: DeltaSpecItems | null;
  preview_text: string;
  would_validate: boolean;
  validation_errors: string[];
  error_code: string | null;
  error_message: string;
  attempts: number;
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

