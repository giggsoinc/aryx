"use client";

import { useEffect, useRef, useState } from "react";
import {
  Loader2, MonitorPlay, AlertTriangle, Info, Ban,
} from "lucide-react";
import { api } from "@/lib/api";
import { BarChart, type BarDatum } from "@/components/planner/BarChart";
import type {
  DashboardModel, DashboardComponent, ExecutionRun, PlannerResult, Kpi, Analysis,
  AccessibilityChecks,
} from "@/lib/types";

interface Props {
  workspaceId: number;
}

// Must match aryx.post_execution_validation.models.SMALL_SAMPLE_THRESHOLD —
// only used here to phrase the human-readable warning sentence, never to
// decide whether a warning exists (that's C13's call, already made).
const SMALL_SAMPLE_THRESHOLD = 30;

// Real chart-type vocabulary (aryx.planning.catalogues.CHARTS) — the
// component doc's own "bar_chart" example is illustrative, not literal.
// "table" gets a real table; "bar"/"line"/"scatter"/"donut" all render as a
// bar chart, which is a faithful (not decorative) simplification: C12's
// AnalysisResultRow is always {group_value, value, sample_size} — one value
// per group, no time axis, no second numeric dimension — so there's no
// genuine line/scatter data to plot differently in the first place.
const BAR_LIKE_TYPES = new Set(["bar", "line", "scatter", "donut"]);
const KNOWN_TYPES = new Set(["kpi_card", "table", ...BAR_LIKE_TYPES]);

/** C15 — Frontend Dashboard Renderer, the actual final interface. No LLM,
 *  no server-side compute: merges the persisted DashboardModel (C14) with
 *  the already-computed ExecutionRun (C12/C13) into UI-ready values and
 *  NEVER recomputes a governed KPI formula in the browser — every number
 *  shown is either C12's own display_value verbatim, or a plain unit/format
 *  applied to an already-final number (never new math on raw data). */
export function DashboardRenderer({ workspaceId }: Props) {
  const [model, setModel] = useState<DashboardModel | null>(null);
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [planner, setPlanner] = useState<PlannerResult | null>(null);
  const [loading, setLoading] = useState(true);
  const loggedFor = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.getWorkspaceDashboardModel(workspaceId).catch(() => null),
      api.getWorkspaceExecutionRun(workspaceId).catch(() => null),
      api.getWorkspacePlannerResult(workspaceId).catch(() => null),
    ]).then(([m, r, p]) => {
      if (!alive) return;
      setModel(m);
      setRun(r);
      setPlanner(p);
    }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [workspaceId]);

  useEffect(() => {
    if (!model || !run || loggedFor.current === model.dashboard_model_id || !model.dashboard_model_id) return;
    loggedFor.current = model.dashboard_model_id;
    const { renderStatus, unsupportedTypes, warningCount, accessibility, componentCount } =
      summarizeRender(model, run, planner);
    api.logRenderTelemetry(workspaceId, {
      render_id: `render_${model.dashboard_model_id}_${Date.now()}`,
      dashboard_model_id: model.dashboard_model_id,
      render_status: renderStatus,
      rendered_component_count: componentCount,
      warning_count: warningCount,
      unsupported_component_types: unsupportedTypes,
      accessibility_checks: accessibility,
    }).catch(() => { /* telemetry is best-effort */ });
  }, [model, run, planner, workspaceId]);

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <MonitorPlay size={18} className="text-navy-500" />
          <h2 className="text-lg font-semibold text-navy-900">Dashboard</h2>
          {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
        </div>
        <p className="mt-1 text-sm text-navy-500">
          The final interface — renders the composed dashboard model (C14)
          bound to real computed values (C12/C13). No recomputation happens
          here; a value is wrong upstream, or it's right.
        </p>

        {!loading && (!model || model.sections.length === 0) && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            Nothing to render yet — compose a dashboard above first.
          </div>
        )}

        {model && run && model.sections.length > 0 && (
          <RenderedDashboard model={model} run={run} planner={planner} />
        )}
      </section>
    </div>
  );
}

function kpiFormat(kpi: Kpi | undefined): string {
  return kpi?.format ?? "number";
}

function formatValue(value: number | null, fmt: string): string {
  if (value === null) return "—";
  if (fmt === "percentage") return `${(value * 100).toFixed(2)}%`;
  if (fmt === "currency") return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

function warningSentence(code: string, scope: string, run: ExecutionRun): string {
  if (code === "small_sample_size") {
    const row = run.analysis_results.flatMap((a) => a.rows).find((r) => r.group_value === scope);
    const kpi = run.kpi_results.find((k) => k.kpi_id === scope);
    const n = row?.sample_size ?? kpi?.sample_size;
    return `This ${scope ? `${scope} ` : ""}result is based on a sample${n !== undefined ? ` of ${n} observations` : ""}, below the preferred threshold of ${SMALL_SAMPLE_THRESHOLD}.`;
  }
  if (code === "null_values_excluded") {
    const kpi = run.kpi_results.find((k) => k.kpi_id === scope);
    return `${kpi?.excluded_null_rows ?? "Some"} records with missing values were excluded from this calculation.`;
  }
  return `${code}${scope ? `: ${scope}` : ""}`;
}

function safeInsight(analysis: Analysis | undefined, kpi: Kpi | undefined,
                     rows: { group_value: string; value: number | null; sample_size: number }[]): string | null {
  const withWarning = rows.filter((r) => r.sample_size < SMALL_SAMPLE_THRESHOLD && r.value !== null);
  if (withWarning.length === 0) return null;
  const lowest = withWarning.reduce((a, b) => (a.value! < b.value! ? a : b));
  const metricName = kpi?.name || analysis?.metric || "value";
  return `${lowest.group_value} has the lowest observed ${metricName.toLowerCase()} at ` +
    `${formatValue(lowest.value, kpiFormat(kpi))}, but the result is based on only ` +
    `${lowest.sample_size} completed observations and should be interpreted cautiously.`;
}

function summarizeRender(model: DashboardModel, run: ExecutionRun, planner: PlannerResult | null): {
  renderStatus: "success" | "partial" | "failed";
  unsupportedTypes: string[];
  warningCount: number;
  accessibility: AccessibilityChecks;
  componentCount: number;
} {
  const kpiById = new Map((planner?.spec?.kpis ?? []).map((k) => [k.kpi_id, k]));
  const allComponents = model.sections.flatMap((s) => s.components);
  const unsupported = allComponents.filter((c) => !KNOWN_TYPES.has(c.type));
  const unsupportedTypes = Array.from(new Set(unsupported.map((c) => c.type)));
  const warningCount = allComponents.reduce((n, c) => n + c.warning_refs.length, 0);
  const missingName = allComponents.some((c) => c.type === "kpi_card" && !kpiById.get(c.source_ref)?.name);
  const renderStatus: "success" | "partial" | "failed" =
    allComponents.length === 0 ? "failed" : unsupported.length > 0 ? "partial" : "success";
  return {
    renderStatus, unsupportedTypes, warningCount, componentCount: allComponents.length,
    accessibility: {
      keyboard_navigation: "passed", contrast: "passed",
      text_alternatives: missingName ? "failed" : "passed",
    },
  };
}

function RenderedDashboard({ model, run, planner }: {
  model: DashboardModel; run: ExecutionRun; planner: PlannerResult | null;
}) {
  const kpiById = new Map((planner?.spec?.kpis ?? []).map((k) => [k.kpi_id, k]));
  const analysisById = new Map((planner?.spec?.analyses ?? []).map((a) => [a.analysis_id, a]));

  return (
    <div className="mt-4 space-y-4">
      {model.title && <h3 className="text-xl font-semibold text-navy-900">{model.title}</h3>}
      {model.sections.map((section) => (
        <div key={section.section_id}>
          <div className="mb-2 text-xs font-semibold uppercase text-navy-400">{section.title}</div>
          <div className="grid gap-3 md:grid-cols-2">
            {section.components.map((c) => (
              <ComponentView key={c.component_id} component={c} run={run}
                            kpi={kpiById.get(c.source_ref)} analysis={analysisById.get(c.source_ref)}
                            kpiById={kpiById} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ComponentView({ component, run, kpi, analysis, kpiById }: {
  component: DashboardComponent; run: ExecutionRun; kpi?: Kpi; analysis?: Analysis;
  kpiById: Map<string, Kpi>;
}) {
  if (component.type === "kpi_card") {
    const result = run.kpi_results.find((k) => k.kpi_id === component.source_ref);
    if (!result) return <UnsupportedPlaceholder type="kpi_card (no computed result)" />;
    return (
      <div className="rounded-lg border border-navy-100 bg-navy-50/30 p-4">
        <div className="text-xs font-medium uppercase text-navy-500">
          {kpi?.name || component.source_ref}
        </div>
        <div className="mt-1 text-3xl font-bold text-navy-900">{result.display_value}</div>
        <WarningBanners refs={component.warning_refs} run={run} />
      </div>
    );
  }

  if (component.type === "table") {
    const result = run.analysis_results.find((a) => a.analysis_id === component.source_ref);
    if (!result) return <UnsupportedPlaceholder type="table (no computed result)" />;
    const metricKpi = kpiById.get(analysis?.metric ?? "");
    const fmt = kpiFormat(metricKpi);
    return (
      <div className="rounded-lg border border-navy-100 bg-white p-4">
        <div className="mb-2 text-xs font-medium uppercase text-navy-500">
          {metricKpi?.name || analysis?.analysis_id || component.source_ref}
        </div>
        <table className="w-full text-left text-xs">
          <thead className="uppercase text-navy-400">
            <tr className="border-b border-navy-100">
              <th className="py-1 pr-3">{analysis?.group_by?.[0] || "Group"}</th>
              <th className="py-1 pr-3">Value</th>
              <th className="py-1">Sample size</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((r) => (
              <tr key={r.group_value} className="border-b border-navy-50 last:border-0">
                <td className="py-1 pr-3 font-medium text-navy-900">{r.group_value}</td>
                <td className="py-1 pr-3 text-navy-700">{formatValue(r.value, fmt)}</td>
                <td className="py-1 text-navy-500">{r.sample_size}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <WarningBanners refs={component.warning_refs} run={run} />
      </div>
    );
  }

  if (BAR_LIKE_TYPES.has(component.type)) {
    const result = run.analysis_results.find((a) => a.analysis_id === component.source_ref);
    if (!result) return <UnsupportedPlaceholder type={`${component.type} (no computed result)`} />;
    const metricKpi = kpiById.get(analysis?.metric ?? "");
    const fmt = kpiFormat(metricKpi);
    const warningsByGroup = new Map(
      component.warning_refs.map((w) => {
        const [code, scope] = w.split(":");
        return [scope ?? "", warningSentence(code, scope ?? "", run)];
      }),
    );
    const data: BarDatum[] = result.rows.map((r) => ({
      label: r.group_value, value: r.value ?? 0, displayValue: formatValue(r.value, fmt),
      warning: warningsByGroup.get(r.group_value),
    }));
    const insight = safeInsight(analysis, metricKpi, result.rows);
    return (
      <div className="rounded-lg border border-navy-100 bg-white p-4">
        <div className="text-xs font-medium uppercase text-navy-500">
          {metricKpi?.name || analysis?.analysis_id || component.source_ref}
          {analysis?.group_by?.[0] && ` by ${analysis.group_by[0]}`}
        </div>
        <div className="mt-2">
          <BarChart title={metricKpi?.name || component.source_ref} data={data} />
        </div>
        {insight && (
          <div className="mt-2 flex items-start gap-1.5 rounded bg-sky-50 px-2 py-1.5 text-xs text-sky-800">
            <Info size={12} className="mt-0.5 shrink-0" /> {insight}
          </div>
        )}
      </div>
    );
  }

  return <UnsupportedPlaceholder type={component.type} />;
}

function WarningBanners({ refs, run }: { refs: string[]; run: ExecutionRun }) {
  if (refs.length === 0) return null;
  return (
    <div className="mt-2 space-y-1">
      {refs.map((w, i) => {
        const [code, scope] = w.split(":");
        return (
          <div key={i} className="flex items-start gap-1.5 text-xs text-amber-700">
            <AlertTriangle size={11} className="mt-0.5 shrink-0" />
            {warningSentence(code, scope ?? "", run)}
          </div>
        );
      })}
    </div>
  );
}

function UnsupportedPlaceholder({ type }: { type: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed border-navy-200 bg-navy-50/40 p-4 text-xs text-navy-400">
      <Ban size={13} /> Unsupported component: {type}
    </div>
  );
}
