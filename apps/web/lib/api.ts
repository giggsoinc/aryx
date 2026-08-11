import type {
  AbResult, AskResponse, Axiom, Brief, DataEntitiesPage, DataSummary,
  Datasource, EntityDetail, EntityGraphView, GraphView, IngestQuestion,
  DatasetIngestResult, DatasetProfile, SemanticProfile, GraphIntakeResult, GraphProfile,
  PlanningContext, PlannerResult, DeltaDraftResult, DeltaSpecItems, ExecutionPlan, ExecutionRun,
  DashboardModel, RenderTelemetry,
  LlmConfig, LlmConfigUpdate, DeriveEntitiesResult, LinkEntitiesResult, OntologyDoc, QuizSpec, ReasonerCheck, Rule,
  SurvivorshipPolicy, UserIntent, UserIntentRequest, Workspace,
} from "./types";

// Same-origin relative path. Next.js rewrites /api/* → FastAPI internally
// (see next.config.mjs). Works in dev (proxies to localhost:8088) and in
// production (proxies to api:8000) without any client-side knowledge.
const BASE = `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/api`;

/** Throw on non-2xx; return parsed JSON otherwise. */
async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listWorkspaces: () =>
    fetchJSON<Workspace[]>("/admin/workspaces?workspace_id=1"),

  createWorkspace: (name: string, description = "") =>
    fetchJSON<Workspace>("/admin/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, description, context: "" }),
    }),

  ask: (question: string, workspaceId: number, history: unknown[] = []) =>
    fetchJSON<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, workspace_id: workspaceId, history }),
    }),

  // ── Accuracy Lab (v2) ────────────────────────────────────────────────
  labAb: (question: string, workspaceId: number) =>
    fetchJSON<AbResult & { error?: string }>("/lab/ab", {
      method: "POST",
      body: JSON.stringify({ question, workspace_id: workspaceId }),
    }),

  labReasoner: (workspaceId: number) =>
    fetchJSON<ReasonerCheck & { error?: string }>(
      `/lab/reasoner?workspace_id=${workspaceId}`,
    ),

  // ── Data Explorer (v2) ───────────────────────────────────────────────
  dataSummary: (workspaceId: number) =>
    fetchJSON<DataSummary & { error?: string }>(
      `/data/summary?workspace_id=${workspaceId}`,
    ),

  dataEntities: (workspaceId: number, type?: string,
                 limit = 50, offset = 0) =>
    fetchJSON<DataEntitiesPage & { error?: string }>(
      `/data/entities?workspace_id=${workspaceId}` +
        (type ? `&type=${encodeURIComponent(type)}` : "") +
        `&limit=${limit}&offset=${offset}`,
    ),

  dataGraph: (workspaceId: number) =>
    fetchJSON<GraphView & { error?: string }>(
      `/data/graph?workspace_id=${workspaceId}`,
    ),

  dataGraphEntity: (workspaceId: number) =>
    fetchJSON<EntityGraphView & { error?: string }>(
      `/data/graph?workspace_id=${workspaceId}&level=entity`,
    ),

  dataEntityDetail: (workspaceId: number, entityId: number) =>
    fetchJSON<EntityDetail & { error?: string }>(
      `/data/entity/${entityId}?workspace_id=${workspaceId}`,
    ),

  // ── Ontology / modelling ──────────────────────────────────────────────
  getOntology: (workspaceId: number) =>
    fetchJSON<OntologyDoc>(`/ontology/types?workspace_id=${workspaceId}`),

  createType: (workspaceId: number, name: string, attributes: string[]) =>
    fetchJSON<{ status: string }>("/ontology/types", {
      method: "POST",
      body: JSON.stringify({ name, attributes, workspace_id: workspaceId }),
    }),

  approveType: (workspaceId: number, name: string) =>
    fetchJSON<{ status: string }>(
      `/ontology/types/${encodeURIComponent(name)}/approve?workspace_id=${workspaceId}`,
      { method: "POST", body: "{}" },
    ),

  setTypeParent: (workspaceId: number, name: string, parent: string | null) =>
    fetchJSON<{ status: string }>(
      `/ontology/types/${encodeURIComponent(name)}/parent?workspace_id=${workspaceId}`,
      { method: "POST", body: JSON.stringify({ parent }) },
    ),

  deleteType: (workspaceId: number, name: string) =>
    fetchJSON<{ status: string }>(
      `/ontology/types/${encodeURIComponent(name)}?workspace_id=${workspaceId}`,
      { method: "DELETE" },
    ),

  deleteRelationshipType: (relId: number) =>
    fetchJSON<{ status: string }>(
      `/ontology/relationships/${relId}`,
      { method: "DELETE" },
    ),

  getAxioms: (workspaceId: number) =>
    fetchJSON<{ axioms: Axiom[] }>(`/ontology/axioms?workspace_id=${workspaceId}`)
      .then((d) => d.axioms || []),

  getRules: (workspaceId: number) =>
    fetchJSON<{ rules: Rule[] }>(`/ontology/rules?workspace_id=${workspaceId}`)
      .then((d) => d.rules || []),

  getSurvivorship: (workspaceId: number) =>
    fetchJSON<{ workspace_id: number; survivorship: SurvivorshipPolicy }>(
      `/admin/workspaces/${workspaceId}/survivorship`,
    ).then((d) => d.survivorship || {}),

  setSurvivorship: (workspaceId: number, policy: SurvivorshipPolicy) =>
    fetchJSON<{ id: number; survivorship: SurvivorshipPolicy }>(
      `/admin/workspaces/${workspaceId}/survivorship`,
      { method: "PUT", body: JSON.stringify(policy) },
    ),

  updateTypeAttrs: (workspaceId: number, name: string,
                    attributes: string[]) =>
    fetchJSON<{ status: string }>("/ontology/types", {
      method: "POST",
      body: JSON.stringify({ name, attributes, workspace_id: workspaceId }),
    }),

  getJob: (jobId: string) =>
    fetchJSON<{
      job_id: string; status: string; stage: string | null;
      pct: number | null; detail: string | null; error: string | null;
    }>(`/admin/jobs/${jobId}`),

  listJobs: (workspaceId: number) =>
    fetchJSON<Array<{
      job_id: string; source_system: string; source_dataset: string;
      status: string; stage: string | null; pct: number | null;
      detail: string | null; error: string | null;
      started_at?: string; finished_at?: string | null;
    }>>(`/admin/jobs?workspace_id=${workspaceId}`),

  getJobEvents: (jobId: string) =>
    fetchJSON<Array<{
      stage: string; pct: number; detail: string; ts: string;
    }>>(`/admin/jobs/${jobId}/events`),

  cancelJob: (jobId: string) =>
    fetchJSON<{ status: string; job_id: string }>(
      `/admin/jobs/${jobId}/cancel`, { method: "POST", body: "{}" },
    ),

  workspaceOverview: () =>
    fetchJSON<Array<{
      id: number; name: string;
      entities: number; relationships: number;
      landed_records: number; running_jobs: number;
    }>>("/admin/workspace-overview"),

  getIngestQuestions: (workspaceId: number, status = "pending") =>
    fetchJSON<IngestQuestion[]>(
      `/admin/ingest-questions?workspace_id=${workspaceId}&status=${status}&limit=50`,
    ),

  answerIngestQuestion: (questionId: number, answer: string,
                         answeredBy = "ui") =>
    fetchJSON<{ id: number; status: string; answer: string }>(
      `/admin/ingest-questions/${questionId}/answer`,
      { method: "POST", body: JSON.stringify({ answer, answered_by: answeredBy }) },
    ),

  getIngestQuestionStats: (workspaceId: number) =>
    fetchJSON<Record<string, number>>(
      `/admin/ingest-questions/stats?workspace_id=${workspaceId}`,
    ),

  // ── Declared relationship types (option g) ───────────────────────────
  listRelationshipTypes: (workspaceId: number) =>
    fetchJSON<Array<{
      id: number; name: string; source_type: string; target_type: string;
    }>>(`/ontology/relationships?workspace_id=${workspaceId}`),

  createRelationshipType: (workspaceId: number, name: string,
                            sourceType: string, targetType: string) =>
    fetchJSON<{ id: number; name: string }>("/ontology/relationships", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: workspaceId, name,
        source_type: sourceType, target_type: targetType,
      }),
    }),

  // ── Explicit post-ingest entity linking (real fk_links, not the
  // cosmetic /ontology/relationships diagram edge above) ─────────────────
  linkEntities: (workspaceId: number, fkLink: {
    source_type: string; source_attr: string;
    target_type: string; target_attr: string; name: string;
  }) =>
    fetchJSON<LinkEntitiesResult>(`/pipeline/link-entities?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify({ fk_links: [fkLink] }),
    }),

  // ── Derive a new type by deduplicating an existing type's column ───────
  deriveEntities: (workspaceId: number, spec: {
    source_type: string; group_by_attr: string;
    new_type_name: string; carry_attrs: string[];
  }) =>
    fetchJSON<DeriveEntitiesResult>(`/pipeline/derive-entities?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify(spec),
    }),

  // ── Wizard / guided setup (Slice W3) ─────────────────────────────────
  draftBrief: (workspaceId: number, seed: string, docText = "") =>
    fetchJSON<{ workspace_id: number; brief: Brief }>(
      `/admin/workspaces/${workspaceId}/draft-brief`,
      {
        method: "POST",
        body: JSON.stringify({ seed, doc_text: docText, workspace_id: workspaceId }),
      },
    ),

  /** Extract plain text from ONE briefing document (PDF/DOC/DOCX/PPT…).
   *  Brief-only reader — the file is never ingested as data. */
  extractBriefDoc: async (workspaceId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${BASE}/admin/workspaces/${workspaceId}/brief-doc-text`,
      { method: "POST", body: form },
    );
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<{
      workspace_id: number; filename: string; chars: number; text: string;
    }>;
  },

  saveBrief: (workspaceId: number, brief: Brief) =>
    fetchJSON<{ id: number; brief: Brief; chain_job_id: string }>(
      `/admin/workspaces/${workspaceId}/brief`,
      { method: "PATCH", body: JSON.stringify(brief) },
    ),

  listDatasourceKinds: () =>
    fetchJSON<{ kinds: Array<{ kind: string; label?: string }>;
                secret_key_configured: boolean }>("/admin/datasources/kinds"),

  getDatasourceQuiz: (kind: string) =>
    fetchJSON<QuizSpec>(`/admin/datasources/quiz?kind=${encodeURIComponent(kind)}`),

  listDatasources: (workspaceId: number) =>
    fetchJSON<Datasource[]>(`/admin/datasources?workspace_id=${workspaceId}`),

  addDatasource: (workspaceId: number, name: string, kind: string,
                  config: Record<string, unknown>, secret = "") =>
    fetchJSON<Datasource>("/admin/datasources", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, name, kind,
                              config, secret }),
    }),

  testDatasource: (datasourceId: number) =>
    fetchJSON<{ ok: boolean; error?: string; tables?: string[];
                 files?: string[] }>(
      `/admin/datasources/${datasourceId}/test`, { method: "POST", body: "{}" },
    ),

  /** Multipart file upload → kicks the file ingest pipeline server-side. */
  uploadFiles: async (workspaceId: number, files: File[], context: string,
                       ontologyType = "Document",
                       matchKeys = "name") => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    form.append("ontology_type", ontologyType);
    form.append("match_keys", matchKeys);
    form.append("context", context);
    form.append("workspace_id", String(workspaceId));
    const res = await fetch(`${BASE}/admin/ingest/file`,
                            { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<{ status: string; job_id: string }>;
  },

  // ── AI ontology assist (option f) ────────────────────────────────────
  suggestAttrs: (workspaceId: number, typeName: string, existing: string[]) =>
    fetchJSON<{ attributes: string[]; rationale: string }>(
      "/ontology/assist/suggest-attrs",
      {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId, type_name: typeName, existing,
        }),
      },
    ),

  // ── Dataset Upload & Ingestion (C02) — read-only; uploads via Onboard ──
  listDatasetVersions: (workspaceId: number, limit = 50) =>
    fetchJSON<DatasetIngestResult[]>(
      `/dataset/versions?workspace_id=${workspaceId}&limit=${limit}`,
    ),

  getDataset: (datasetId: string, workspaceId: number) =>
    fetchJSON<DatasetIngestResult>(
      `/dataset/${encodeURIComponent(datasetId)}?workspace_id=${workspaceId}`,
    ),

  // ── Deterministic Dataset Profiler (C03) ─────────────────────────────
  getProfile: (datasetId: string, workspaceId: number) =>
    fetchJSON<DatasetProfile>(
      `/profile/${encodeURIComponent(datasetId)}?workspace_id=${workspaceId}`,
    ),

  // ── Semantic Field Interpreter (C04) ─────────────────────────────────
  getSemantic: (datasetId: string, workspaceId: number) =>
    fetchJSON<SemanticProfile>(
      `/semantic/${encodeURIComponent(datasetId)}?workspace_id=${workspaceId}`,
    ),

  // ── Context and Resource Retrieval (C07) ─────────────────────────────
  getPlanningContext: (datasetId: string, workspaceId: number) =>
    fetchJSON<PlanningContext>(
      `/planning-context/${encodeURIComponent(datasetId)}?workspace_id=${workspaceId}`,
    ),

  getWorkspacePlanningContext: (workspaceId: number) =>
    fetchJSON<PlanningContext>(`/planning-context/workspace?workspace_id=${workspaceId}`),

  runWorkspacePlanningContext: (workspaceId: number) =>
    fetchJSON<PlanningContext>(`/planning-context/workspace/run?workspace_id=${workspaceId}`, {
      method: "POST",
      body: "{}",
    }),

  // ── Andie Jr Planning Orchestrator (C08) — on-demand, calls a real LLM ──
  runAndiePlanner: (datasetId: string, workspaceId: number) =>
    fetchJSON<PlannerResult>(`/andie-planner/run?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: datasetId }),
    }),

  runAndiePlannerWorkspace: (workspaceId: number) =>
    fetchJSON<PlannerResult>(`/andie-planner/workspace/run?workspace_id=${workspaceId}`, {
      method: "POST",
      body: "{}",
    }),

  listAndiePlans: (workspaceId: number, limit = 50) =>
    fetchJSON<PlannerResult[]>(
      `/andie-planner/versions?workspace_id=${workspaceId}&limit=${limit}`,
    ),

  // ── Ask-to-visualize (C08 extension) — draft, preview, confirm ───────
  draftDelta: (workspaceId: number, datasetId: string, requestText: string) =>
    fetchJSON<DeltaDraftResult>(`/andie-planner/delta/draft?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: datasetId, request_text: requestText }),
    }),

  confirmDelta: (workspaceId: number, datasetId: string, items: DeltaSpecItems) =>
    fetchJSON<PlannerResult>(`/andie-planner/delta/confirm?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify({
        dataset_id: datasetId, new_kpi: items.new_kpi, new_analysis: items.new_analysis,
        new_visualization: items.new_visualization,
      }),
    }),

  // ── Knowledge Graph Intake & Validation (C05) ────────────────────────
  runGraphIntake: (workspaceId: number) =>
    fetchJSON<GraphIntakeResult>(`/graph-intake/run?workspace_id=${workspaceId}`, {
      method: "POST",
      body: "{}",
    }),

  listGraphVersions: (workspaceId: number, limit = 50) =>
    fetchJSON<GraphIntakeResult[]>(
      `/graph-intake/versions?workspace_id=${workspaceId}&limit=${limit}`,
    ),

  // ── Knowledge Graph Profiler (C06) ───────────────────────────────────
  getGraphProfile: (workspaceId: number) =>
    fetchJSON<GraphProfile>(
      `/graph-profile/graph_workspace_${workspaceId}?workspace_id=${workspaceId}`,
    ),

  // ── Execution Compiler (C11) — read-only; no LLM ─────────────────────
  getExecutionPlan: (datasetId: string, workspaceId: number) =>
    fetchJSON<ExecutionPlan>(
      `/execution-plan/${encodeURIComponent(datasetId)}?workspace_id=${workspaceId}`,
    ),

  listExecutionPlans: (workspaceId: number, limit = 50) =>
    fetchJSON<ExecutionPlan[]>(
      `/execution-plan/versions?workspace_id=${workspaceId}&limit=${limit}`,
    ),

  // ── Deterministic Analysis Execution (C12) — on-demand; no LLM ────────
  runExecutionForWorkspace: (workspaceId: number) =>
    fetchJSON<ExecutionRun>(`/execution-run/run?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify({ dataset_id: `workspace_${workspaceId}` }),
    }),

  getWorkspaceExecutionRun: (workspaceId: number) =>
    fetchJSON<ExecutionRun | null>(`/execution-run/workspace?workspace_id=${workspaceId}`),

  // C13's post-execution validation report rides along on ExecutionRun
  // (.validation) — this is the log of past runs/validations, newest first.
  listWorkspaceExecutionRuns: (workspaceId: number, limit = 50) =>
    fetchJSON<ExecutionRun[]>(
      `/execution-run/versions?dataset_id=workspace_${workspaceId}&workspace_id=${workspaceId}&limit=${limit}`,
    ),

  // ── Dashboard Composition (C14) — on-demand; hybrid, LLM optional ──────
  composeWorkspaceDashboard: (workspaceId: number, audience: string, useLlm: boolean) =>
    fetchJSON<DashboardModel>(`/dashboard-model/run?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify({
        dataset_id: `workspace_${workspaceId}`, audience, use_llm: useLlm,
      }),
    }),

  getWorkspaceDashboardModel: (workspaceId: number) =>
    fetchJSON<DashboardModel | null>(`/dashboard-model/workspace?workspace_id=${workspaceId}`),

  // ── Frontend Dashboard Renderer (C15) — telemetry only, no compute ─────
  getWorkspacePlannerResult: (workspaceId: number) =>
    fetchJSON<PlannerResult>(`/andie-planner/workspace?workspace_id=${workspaceId}`),

  logRenderTelemetry: (workspaceId: number, telemetry: RenderTelemetry) =>
    fetchJSON<{ status: string }>(`/render-telemetry/log?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify(telemetry),
    }),

  // ── User Intent Capture (C01) ────────────────────────────────────────
  captureIntent: (req: UserIntentRequest, workspaceId: number) =>
    fetchJSON<UserIntent>(`/intent/capture?workspace_id=${workspaceId}`, {
      method: "POST",
      body: JSON.stringify(req),
    }),

  listIntents: (workspaceId: number, limit = 50) =>
    fetchJSON<UserIntent[]>(
      `/intent/captures?workspace_id=${workspaceId}&limit=${limit}`,
    ),

  // ── LLM provider (runtime; process memory — not persisted to disk) ──
  getLlmConfig: () => fetchJSON<LlmConfig>("/llm/config"),

  // ── Corrections: fix now + standing rule replayed on every ingest ─────
  addCorrection: (workspaceId: number, body: {
    kind: "retype" | "remove" | "link" | "unlink" | "merge" | "rename_type";
    entity_id?: number; target_id?: number; name?: string; type_name?: string;
  }) =>
    fetchJSON<{ id: number; kind: string; subject: string; object: string }>(
      `/admin/workspaces/${workspaceId}/corrections`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  /** Plain-language correction (graph chat drawer) — write-only, not Ask.
   *  Returns a PROPOSAL; nothing is applied until addCorrection is called
   *  with the returned action. */
  correctionChat: (workspaceId: number, text: string, selectedEntityId = 0) =>
    fetchJSON<{
      status: string; message: string;
      action?: {
        kind: "retype" | "remove" | "link" | "unlink" | "merge" | "rename_type";
        entity_id?: number; target_id?: number; name?: string; type_name?: string;
      };
    }>(
      `/admin/workspaces/${workspaceId}/corrections/chat`,
      { method: "POST",
        body: JSON.stringify({ text, selected_entity_id: selectedEntityId }) },
    ),

  listCorrections: (workspaceId: number) =>
    fetchJSON<Array<{
      id: number; kind: string; subject: string;
      object: string; detail: string; created_at: string;
    }>>(`/admin/workspaces/${workspaceId}/corrections`),

  deleteCorrection: (correctionId: number) =>
    fetchJSON<{ status: string }>(`/admin/corrections/${correctionId}`,
      { method: "DELETE" }),

  /** Wipe this workspace's data (records/entities/links/graph) for a clean
   *  re-ingest. Brief, model choice, types, and corrections survive. */
  resetWorkspaceData: (workspaceId: number) =>
    fetchJSON<{ workspace_id: number; deleted: Record<string, number> }>(
      `/admin/workspaces/${workspaceId}/reset-data`,
      { method: "POST", body: "{}" },
    ),

  /** Permanently delete a workspace (Default / id=1 is rejected by the API). */
  deleteWorkspace: (workspaceId: number) =>
    fetchJSON<{ status: string; workspace_id: number }>(
      `/admin/workspaces/${workspaceId}`,
      { method: "DELETE" },
    ),

  /** Installed local Ollama models for the Home picker. */
  listLlmModels: () =>
    fetchJSON<{ ok: boolean; models: string[]; error?: string; endpoint?: string }>(
      "/llm/models"),

  /** Product / runtime version for Settings. */
  getVersion: () =>
    fetchJSON<{
      product: string; version: string; api: string;
      python: string; platform: string;
    }>("/version"),

  /** Physical storage truth: what is ACTUALLY in Postgres + FalkorDB, plus
   *  service health. Counts come from the stores, never from job claims. */
  systemStatus: () =>
    fetchJSON<{
      postgres: {
        ok: boolean; error?: string; db_size?: string;
        doc_chunks?: number; chunk_embeddings?: number;
        workspaces: Array<{
          id: number; name: string; landed_records: number;
          entities: number; relationships: number;
        }>;
      };
      falkordb: {
        ok: boolean; error?: string;
        graphs: Array<{ workspace_id: number; nodes: number; edges: number }>;
      };
      llm: { ok: boolean; provider: string; model: string; detail: string };
    }>("/admin/system/status"),

  /** Config + reachability — false while Ollama is still pulling models. */
  getLlmHealth: () =>
    fetchJSON<{ ok: boolean; provider: string; model: string; detail: string }>(
      "/llm/health"),

  setLlmConfig: (cfg: LlmConfigUpdate) =>
    fetchJSON<LlmConfig>("/admin/llm/config", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),
};
