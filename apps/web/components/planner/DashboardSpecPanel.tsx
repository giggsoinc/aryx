"use client";

import { useEffect, useState } from "react";
import {
  Sparkles, Loader2, CheckCircle2, XCircle, AlertTriangle, ChevronDown, Database,
} from "lucide-react";
import { api } from "@/lib/api";
import type { DashboardSpec, PlannerResult } from "@/lib/types";

interface Props {
  workspaceId: number;
}

const WORKSPACE_SENTINEL = "__workspace__";

function displayDatasetId(id: string): string {
  return id.startsWith("workspace_") ? "🌐 Whole workspace" : id;
}

/** C08 — Andie Jr Planning Orchestrator. On-demand only: this is the first
 *  component that calls a real LLM, so it never auto-runs on ingest. Andie
 *  drafts a candidate, non-executable dashboard spec; every column/operation/
 *  chart/cross-reference is code-verified (ground.py) before display — the
 *  model's raw output is never trusted or shown directly. */
export function DashboardSpecPanel({ workspaceId }: Props) {
  const [datasetIds, setDatasetIds] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PlannerResult | null>(null);
  const [recent, setRecent] = useState<PlannerResult[]>([]);

  useEffect(() => {
    // Show the last valid spec for THIS workspace until a new one is
    // composed — never a prior workspace's result lingering, and never
    // blank just because of a navigation/refresh (mirrors
    // DashboardModelPanel's persisted-on-mount fetch). `alive` guards
    // against a slow fetch for a workspace the user has since switched
    // away from overwriting the newer workspace's state.
    let alive = true;
    api.getWorkspacePlannerResult(workspaceId)
      .then((r) => { if (alive) setResult(r); })
      .catch(() => { if (alive) setResult(null); });
    api.listDatasetVersions(workspaceId).then((rows) => {
      const ids = Array.from(new Set(rows.map((r) => r.dataset_id)));
      setDatasetIds(ids);
      // Re-validate the current selection against THIS workspace's list —
      // a value carried over from a previous workspace may no longer exist,
      // which desyncs the visible <select> (browser shows option 0) from
      // the submitted value (still the stale one) unless reset here.
      setSelected((prev) => (
        prev && (prev === WORKSPACE_SENTINEL || ids.includes(prev)) ? prev : (ids[0] ?? "")
      ));
    }).catch(() => { setDatasetIds([]); setSelected(""); });
    api.listAndiePlans(workspaceId).then(setRecent).catch(() => setRecent([]));
    return () => { alive = false; };
  }, [workspaceId]);

  const generate = async () => {
    if (!selected) return;
    setRunning(true);
    setResult(null);
    try {
      const res = selected === WORKSPACE_SENTINEL
        ? await api.runAndiePlannerWorkspace(workspaceId)
        : await api.runAndiePlanner(selected, workspaceId);
      setResult(res);
      api.listAndiePlans(workspaceId).then(setRecent).catch(() => {});
    } catch (e) {
      setResult({
        status: "controlled_error", spec: null,
        error_code: "request_failed",
        error_message: e instanceof Error ? e.message : String(e),
        attempts: 0, validation: null, analysis_datasets: [], execution_plans: [],
        created_at: new Date().toISOString(),
      });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-navy-500" />
          <h2 className="text-lg font-semibold text-navy-900">Dashboard Spec</h2>
          <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs font-medium text-violet-700">
            LLM-drafted · code-grounded
          </span>
        </div>
        <p className="mt-1 text-sm text-navy-500">
          Andie drafts business questions, KPIs, analyses, and charts from the
          approved planning context — never a computed value, never a causal
          claim. Every reference is verified before you see it; unsupported
          ones are dropped and listed as warnings, not silently invented.
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div className="relative">
            <select value={selected} onChange={(e) => setSelected(e.target.value)}
                    className="appearance-none rounded-lg border border-navy-200 py-2 pl-3 pr-8 text-sm text-navy-900 focus-ring">
              {datasetIds.length === 0 && <option value="">No datasets yet</option>}
              {datasetIds.length > 0 && (
                <option value={WORKSPACE_SENTINEL}>🌐 Whole workspace</option>
              )}
              {datasetIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
            <ChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-navy-400" />
          </div>
          <button onClick={generate} disabled={running || !selected}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-900 px-4 py-2 text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-60">
            {running && <Loader2 size={15} className="animate-spin" />}
            {running ? "Drafting (real LLM call, ~10–20s)…" : "Generate spec"}
          </button>
        </div>

        {result && <ResultView result={result} />}

        {recent.length > 0 && (
          <div className="mt-4">
            <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
              Recent runs
            </div>
            <ul className="space-y-1">
              {recent.map((r, i) => (
                <li key={i} className="flex items-center gap-3 rounded-lg border border-navy-100 px-3 py-1.5 text-sm">
                  <span className="font-medium text-navy-700">
                    {r.spec ? displayDatasetId(r.spec.dataset_id) : "—"}
                  </span>
                  <span className="text-navy-500">
                    {r.spec ? `${r.spec.kpis.length} KPIs · ${r.spec.warnings.length} warnings` : r.error_code}
                  </span>
                  <StatusPill status={r.status} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

function ResultView({ result }: { result: PlannerResult }) {
  if (result.status === "controlled_error") {
    return (
      <div className="mt-4 rounded-lg border border-red-200 bg-red-50/50 p-4">
        <div className="flex items-center gap-2 font-semibold text-red-800">
          <XCircle size={17} /> Controlled error — {result.error_code}
        </div>
        <p className="mt-1 text-sm text-red-700">{result.error_message}</p>
        <p className="mt-1 text-xs text-red-500">
          Attempts: {result.attempts}. No spec was produced — nothing was guessed.
        </p>
      </div>
    );
  }
  if (result.status === "controlled_failure") {
    const v = result.validation;
    return (
      <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50/50 p-4">
        <div className="flex items-center gap-2 font-semibold text-rose-800">
          <XCircle size={17} /> Controlled failure — {result.error_code}
        </div>
        <p className="mt-1 text-sm text-rose-700">
          The candidate spec ({result.spec?.spec_id}) was rejected by
          pre-execution validation (C09) on both the initial attempt and its
          one allowed repair retry. Execution never started.
        </p>
        {v && v.errors.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {v.errors.map((e, i) => (
              <span key={i} title={`${e.path} → ${e.reference}`}
                    className="rounded bg-rose-100 px-2 py-0.5 text-xs text-rose-800">
                {e.code}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }
  const spec = result.spec!;
  return (
    <div className={`mt-4 rounded-lg border p-4 ${spec.spec_status === "valid" ? "border-emerald-200 bg-emerald-50/30" : "border-amber-200 bg-amber-50/30"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-semibold text-navy-900">
          {spec.spec_status === "valid"
            ? <CheckCircle2 size={17} className="text-emerald-600" />
            : <AlertTriangle size={17} className="text-amber-600" />}
          {spec.spec_id}
          <StatusPill status={result.status} />
        </div>
        <span className="text-xs text-navy-400">
          {displayDatasetId(spec.dataset_id)} · {spec.model_name} · {spec.model_tier} tier
        </span>
      </div>

      <RichnessIndicator spec={spec} />

      <div className="mt-3">
        <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
          Business questions ({spec.business_questions.length})
        </div>
        <ul className="list-disc space-y-0.5 pl-5 text-sm text-navy-800">
          {spec.business_questions.map((q) => <li key={q.question_id}>{q.text}</li>)}
        </ul>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
            KPIs ({spec.kpis.length})
          </div>
          <div className="space-y-1">
            {spec.kpis.map((k) => (
              <div key={k.kpi_id} className="rounded bg-white px-2 py-1 text-xs ring-1 ring-navy-100">
                <span className="font-medium text-navy-800">{k.name}</span>{" "}
                <span className="text-sky-600">{k.operation}</span>{" "}
                <span className="text-navy-400">
                  {(k.source_columns.length ? k.source_columns : k.measure ? [k.measure] : []).join(", ")}
                </span>
                <span className="ml-1 rounded bg-navy-50 px-1 text-navy-500">{k.format}</span>
                {k.dataset_id && (
                  <span className="ml-1 rounded bg-violet-50 px-1 text-violet-600">{k.dataset_id}</span>
                )}
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
            Visualizations ({spec.visualizations.length})
          </div>
          <div className="space-y-1">
            {spec.visualizations.map((v) => (
              <div key={v.chart_id} className="rounded bg-white px-2 py-1 text-xs ring-1 ring-navy-100">
                <span className="rounded bg-violet-50 px-1 text-violet-700">{v.chart_type}</span>{" "}
                <span className="text-navy-600">→ {v.source_ref}</span>
              </div>
            ))}
            {spec.visualizations.length === 0 && (
              <p className="text-xs text-navy-400">None survived grounding.</p>
            )}
          </div>
        </div>
      </div>

      {spec.assumptions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {spec.assumptions.map((a, i) => (
            <span key={i} className="rounded bg-sky-50 px-2 py-0.5 text-xs text-sky-800">
              {a.code}: {a.meaning}
            </span>
          ))}
        </div>
      )}

      {spec.warnings.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-navy-700">
            <AlertTriangle size={12} className="text-amber-500" /> Grounding warnings
            (unsupported content — dropped, not shown above)
          </div>
          <div className="flex flex-wrap gap-1">
            {spec.warnings.map((w, i) => (
              <span key={i} title={w.detail} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
                {w.code}
              </span>
            ))}
          </div>
        </div>
      )}

      {result.validation && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-navy-500">
          <CheckCircle2 size={12} className="text-emerald-500" />
          Pre-execution validation (C09): {result.validation.status}
          {" · "}{result.validation.checks.length} checks
          {result.validation.attempt > 1 && ` · recovered on retry ${result.validation.attempt}`}
        </div>
      )}

      {result.analysis_datasets.length > 0 && (
        <div className="mt-3 space-y-2">
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-navy-400">
            <Database size={12} /> Analysis-ready dataset (C10)
          </div>
          {result.analysis_datasets.map((ad) => (
            <div key={ad.analysis_dataset_id}
                 className={`rounded-lg border p-2 text-xs ${ad.status === "ready_with_warnings" ? "border-amber-200 bg-amber-50/40" : "border-navy-100 bg-white"}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium text-navy-800">{ad.source_dataset_id}</span>
                <span className="text-navy-500">{ad.row_count} rows · {ad.status}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {ad.transformations.map((t, i) => (
                  <span key={i}
                        title={`${t.failed_rows} failed · ${t.changed_rows} changed`}
                        className={`rounded px-1.5 py-0.5 ${t.reverted ? "bg-amber-100 text-amber-800" : "bg-navy-50 text-navy-600"}`}>
                    {t.column}: {t.operation}{t.reverted ? " (reverted)" : ""}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: PlannerResult["status"] }) {
  const cls = status === "controlled_error" || status === "controlled_failure" ? "bg-red-100 text-red-700"
    : status === "invalid" ? "bg-amber-100 text-amber-700"
    : "bg-emerald-100 text-emerald-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

// Observability only — never blocks or rejects a spec (C09 already owns
// correctness). A "thin" spec still renders exactly as generated; this just
// makes the gap visible instead of only being caught by a human reading it,
// closing the Kaizen "measurement gap" found while investigating why
// generated specs tend to come out primitive.
const MIN_RICH_KPIS = 3;
const MIN_RICH_VISUALIZATIONS = 4;
const SUBSTANTIVE_ASSUMPTION_MIN_LENGTH = 40;

function RichnessIndicator({ spec }: { spec: DashboardSpec }) {
  const kpiCount = spec.kpis.length;
  const analysisCount = spec.analyses.length;
  const vizCount = spec.visualizations.length;
  const substantiveAssumptions = spec.assumptions.filter(
    (a) => a.meaning.length >= SUBSTANTIVE_ASSUMPTION_MIN_LENGTH).length;
  const isThin = kpiCount < MIN_RICH_KPIS || vizCount < MIN_RICH_VISUALIZATIONS
    || substantiveAssumptions === 0;

  return (
    <div className={`mt-2 flex items-center gap-1.5 text-xs ${isThin ? "text-amber-700" : "text-navy-500"}`}
        title={isThin
          ? "Fewer KPIs/visualizations or shallower reasoning than usual — still a valid spec, just worth a second look."
          : "Within the usual range for KPI/visualization count and assumption depth."}>
      {isThin && <AlertTriangle size={12} className="shrink-0 text-amber-500" />}
      Richness: {kpiCount} KPIs &middot; {analysisCount} analyses &middot; {vizCount} visualizations &middot;{" "}
      {substantiveAssumptions}/{spec.assumptions.length} substantive assumptions
    </div>
  );
}
