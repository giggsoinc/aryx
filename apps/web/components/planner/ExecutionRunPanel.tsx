"use client";

import { useEffect, useState } from "react";
import {
  Loader2, PlayCircle, CheckCircle2, XCircle, AlertTriangle, Gauge,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ExecutionRun, KpiResult, AnalysisResult } from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** C12 — Deterministic Analysis Execution. On-demand only, like C08: this
 *  runs the compiled C11 plan against real data and produces the first real
 *  KPI values — nothing computes until you press Run. No LLM. */
export function ExecutionRunPanel({ workspaceId }: Props) {
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let alive = true;
    api.getWorkspaceExecutionRun(workspaceId)
      .then((r) => { if (alive) setRun(r); })
      .catch(() => { if (alive) setRun(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [workspaceId]);

  const trigger = async () => {
    setRunning(true);
    try {
      const r = await api.runExecutionForWorkspace(workspaceId);
      setRun(r);
    } catch (e) {
      setRun({
        execution_run_id: "", execution_plan_id: "", spec_id: "",
        dataset_id: `workspace_${workspaceId}`, dataset_version: "",
        status: "failed", kpi_results: [], analysis_results: [],
        execution_metrics: { runtime_ms: 0, nodes_completed: 0, nodes_failed: 0 },
        errors: [e instanceof Error ? e.message : String(e)],
        created_at: new Date().toISOString(),
      });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gauge size={18} className="text-navy-500" />
            <h2 className="text-lg font-semibold text-navy-900">Analysis Execution</h2>
            {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
          </div>
          <button onClick={trigger} disabled={running}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-900 px-4 py-2 text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-60">
            {running ? <Loader2 size={15} className="animate-spin" /> : <PlayCircle size={15} />}
            {running ? "Running…" : "Run analysis"}
          </button>
        </div>
        <p className="mt-1 text-sm text-navy-500">
          C12 runs the compiled execution plan (C11) against real, C10-converted
          rows and produces the first real KPI values and per-group breakdowns
          — deterministic, no LLM. Runs only when you press the button.
        </p>

        {!run && !loading && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            No run yet — press "Run analysis" once a workspace-wide dashboard
            spec and its execution plan exist.
          </div>
        )}

        {run && <RunView run={run} />}
      </section>
    </div>
  );
}

function RunView({ run }: { run: ExecutionRun }) {
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-navy-500">
        <StatusPill status={run.status} />
        <span>{run.execution_metrics.runtime_ms} ms</span>
        <span>{run.execution_metrics.nodes_completed} nodes completed</span>
        {run.execution_metrics.nodes_failed > 0 && (
          <span className="text-red-600">{run.execution_metrics.nodes_failed} failed</span>
        )}
        {run.execution_run_id && <code className="text-navy-400">{run.execution_run_id}</code>}
      </div>

      {run.errors.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50/50 p-3">
          {run.errors.map((e, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-red-700">
              <XCircle size={12} className="mt-0.5 shrink-0" /> {e}
            </div>
          ))}
        </div>
      )}

      {run.kpi_results.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
            KPI results ({run.kpi_results.length})
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {run.kpi_results.map((k) => <KpiCard key={k.kpi_id} kpi={k} />)}
          </div>
        </div>
      )}

      {run.analysis_results.map((a) => <AnalysisTable key={a.analysis_id} analysis={a} />)}
    </div>
  );
}

function KpiCard({ kpi }: { kpi: KpiResult }) {
  return (
    <div className="rounded-lg border border-navy-100 bg-navy-50/30 p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs font-medium text-navy-800">{kpi.kpi_id}</span>
        <span className="text-lg font-semibold text-navy-900">{kpi.display_value}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-navy-500">
        {kpi.numerator !== null && kpi.denominator !== null && (
          <span>{kpi.numerator} / {kpi.denominator}</span>
        )}
        <span>sample size {kpi.sample_size}</span>
        {kpi.excluded_null_rows > 0 && (
          <span className="text-amber-600">{kpi.excluded_null_rows} nulls excluded</span>
        )}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {kpi.lineage.source_columns.map((c) => (
          <span key={c} className="rounded bg-white px-1.5 py-0.5 text-[11px] text-navy-600 ring-1 ring-navy-100">
            {c}
          </span>
        ))}
      </div>
    </div>
  );
}

function AnalysisTable({ analysis }: { analysis: AnalysisResult }) {
  const hasRatio = analysis.rows.some((r) => r.numerator !== null);
  return (
    <div className="rounded-lg border border-navy-100 bg-white p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-navy-400">
        {analysis.analysis_id} — by {analysis.group_column}
      </div>
      <table className="w-full text-left text-xs">
        <thead className="uppercase text-navy-400">
          <tr className="border-b border-navy-100">
            <th className="py-1 pr-3">{analysis.group_column}</th>
            {hasRatio && <th className="py-1 pr-3">Numerator / Denominator</th>}
            <th className="py-1 pr-3">Value</th>
            <th className="py-1">Sample size</th>
          </tr>
        </thead>
        <tbody>
          {analysis.rows.map((r) => (
            <tr key={r.group_value} className="border-b border-navy-50 last:border-0">
              <td className="py-1 pr-3 font-medium text-navy-900">{r.group_value}</td>
              {hasRatio && (
                <td className="py-1 pr-3 text-navy-500">
                  {r.numerator !== null ? `${r.numerator} / ${r.denominator}` : "—"}
                </td>
              )}
              <td className="py-1 pr-3 text-navy-700">
                {r.value !== null ? r.value.toLocaleString(undefined, { maximumFractionDigits: 4 }) : "—"}
              </td>
              <td className="py-1 text-navy-500">{r.sample_size}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ status }: { status: ExecutionRun["status"] }) {
  const cls = status === "failed" ? "bg-red-100 text-red-700"
    : status === "partial" ? "bg-amber-100 text-amber-700"
    : "bg-emerald-100 text-emerald-700";
  const Icon = status === "failed" ? XCircle : status === "partial" ? AlertTriangle : CheckCircle2;
  return (
    <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${cls}`}>
      <Icon size={12} /> {status}
    </span>
  );
}
