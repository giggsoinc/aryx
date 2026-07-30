import type {
  AbResult, AskResponse, Axiom, Brief, DataEntitiesPage, DataSummary,
  Datasource, EntityDetail, EntityGraphView, GraphView, IngestQuestion,
  DatasetIngestResult, DatasetProfile, SemanticProfile, GraphIntakeResult, GraphProfile,
  PlanningContext, PlannerResult, ExecutionPlan, ExecutionRun, DashboardModel,
  LlmConfig, LlmConfigUpdate, OntologyDoc, QuizSpec, ReasonerCheck, Rule,
  SurvivorshipPolicy, UserIntent, UserIntentRequest, Workspace,
} from "./types";

// Same-origin relative path. Next.js rewrites /api/* → FastAPI internally
// (see next.config.mjs). Works in dev (proxies to localhost:8088) and in
// production (proxies to api:8000) without any client-side knowledge.
const BASE = "/api";

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

  // ── Wizard / guided setup (Slice W3) ─────────────────────────────────
  draftBrief: (workspaceId: number, seed: string, docText = "") =>
    fetchJSON<{ workspace_id: number; brief: Brief }>(
      `/admin/workspaces/${workspaceId}/draft-brief`,
      {
        method: "POST",
        body: JSON.stringify({ seed, doc_text: docText, workspace_id: workspaceId }),
      },
    ),

  saveBrief: (workspaceId: number, brief: Brief) =>
    fetchJSON<{ id: number; brief: Brief }>(
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
  uploadFiles: async (workspaceId: number, files: File[],
                       ontologyType = "Document",
                       matchKeys = "name") => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    form.append("ontology_type", ontologyType);
    form.append("match_keys", matchKeys);
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

  setLlmConfig: (cfg: LlmConfigUpdate) =>
    fetchJSON<LlmConfig>("/admin/llm/config", {
      method: "POST",
      body: JSON.stringify(cfg),
    }),
};
