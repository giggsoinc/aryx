"use client";

import { useEffect, useState } from "react";
import {
  Loader2, LayoutDashboard, Sparkles, CheckCircle2, XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  DashboardModel, DashboardSection, DashboardComponent, ExecutionRun,
} from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** C14 — Dashboard Composition. On-demand only, like C08/C12 — gated on
 *  C13's eligible_for_dashboard (composition refuses to run against results
 *  that weren't validated). Hybrid: the optional "narrate with LLM" toggle
 *  may only suggest section titles — it can never add, remove, or rebind a
 *  component; the deterministic layout is always the fallback. */
export function DashboardModelPanel({ workspaceId }: Props) {
  const [model, setModel] = useState<DashboardModel | null>(null);
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [composing, setComposing] = useState(false);
  const [audience, setAudience] = useState("");
  const [useLlm, setUseLlm] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.getWorkspaceDashboardModel(workspaceId).catch(() => null),
      api.getWorkspaceExecutionRun(workspaceId).catch(() => null),
    ]).then(([m, r]) => {
      if (!alive) return;
      setModel(m);
      setRun(r);
    }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [workspaceId]);

  const trigger = async () => {
    setComposing(true);
    try {
      const m = await api.composeWorkspaceDashboard(workspaceId, audience, useLlm);
      setModel(m);
    } catch (e) {
      setModel({
        dashboard_model_id: "", spec_id: "", dataset_id: `workspace_${workspaceId}`,
        dataset_version: "", title: "", audience, sections: [], max_columns: 3,
        composition_status: "invalid",
        issues: [{ code: "request_failed", reference: "",
                  detail: e instanceof Error ? e.message : String(e) }],
        composed_by: "deterministic", created_at: new Date().toISOString(),
      });
    } finally {
      setComposing(false);
    }
  };

  const kpiDisplay = (sourceRef: string): string | null =>
    run?.kpi_results.find((k) => k.kpi_id === sourceRef)?.display_value ?? null;

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <LayoutDashboard size={18} className="text-navy-500" />
            <h2 className="text-lg font-semibold text-navy-900">Dashboard Composition</h2>
            {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
          </div>
        </div>
        <p className="mt-1 text-sm text-navy-500">
          C14 arranges the validated results (C13) into an ordered dashboard —
          it can group and title, but never alter a value, formula, axis, or ID.
          Also runs automatically once execution results are eligible (see the
          Jobs panel); use the button to force a fresh composition on demand.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input value={audience} onChange={(e) => setAudience(e.target.value)}
                placeholder="Audience (e.g. sales leadership)"
                className="w-56 rounded-lg border border-navy-200 px-3 py-2 text-sm text-navy-900 outline-none focus:border-navy-300" />
          <label className="flex items-center gap-1.5 text-sm text-navy-700">
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
            <Sparkles size={13} className="text-violet-500" /> Narrate with LLM (optional)
          </label>
          <button onClick={trigger} disabled={composing}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-900 px-4 py-2 text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-60">
            {composing && <Loader2 size={15} className="animate-spin" />}
            {composing ? "Composing…" : "Re-run manually"}
          </button>
        </div>

        {!model && !loading && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            No dashboard composed yet.
          </div>
        )}

        {model && <ModelView model={model} kpiDisplay={kpiDisplay} />}
      </section>
    </div>
  );
}

function ModelView({ model, kpiDisplay }: {
  model: DashboardModel; kpiDisplay: (ref: string) => string | null;
}) {
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-navy-500">
        <StatusPill status={model.composition_status} />
        {model.composed_by === "llm_assisted" && (
          <span className="flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 font-medium text-violet-700">
            <Sparkles size={11} /> LLM-narrated
          </span>
        )}
        {model.title && <span className="font-semibold text-navy-800">{model.title}</span>}
        {model.dashboard_model_id && <code className="text-navy-400">{model.dashboard_model_id}</code>}
      </div>

      {model.issues.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50/50 p-3">
          {model.issues.map((iss, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-red-700">
              <XCircle size={12} className="mt-0.5 shrink-0" />
              {iss.code}{iss.reference ? ` · ${iss.reference}` : ""}{iss.detail ? ` — ${iss.detail}` : ""}
            </div>
          ))}
        </div>
      )}

      {model.sections.map((s) => (
        <SectionView key={s.section_id} section={s} kpiDisplay={kpiDisplay} />
      ))}
    </div>
  );
}

function SectionView({ section, kpiDisplay }: {
  section: DashboardSection; kpiDisplay: (ref: string) => string | null;
}) {
  return (
    <div className="rounded-lg border border-navy-100 bg-navy-50/30 p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-navy-400">{section.title}</div>
      <div className="grid gap-2 md:grid-cols-3">
        {section.components.map((c) => (
          <ComponentCard key={c.component_id} component={c} kpiDisplay={kpiDisplay} />
        ))}
      </div>
    </div>
  );
}

function ComponentCard({ component, kpiDisplay }: {
  component: DashboardComponent; kpiDisplay: (ref: string) => string | null;
}) {
  const display = component.type === "kpi_card" ? kpiDisplay(component.source_ref) : null;
  return (
    <div className="rounded-lg border border-navy-100 bg-white p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">{component.type}</span>
        <span className="text-navy-400">#{component.position}</span>
      </div>
      <div className="mt-1 font-mono text-navy-600">{component.source_ref}</div>
      {display !== null && (
        <div className="mt-1 text-lg font-semibold text-navy-900">{display}</div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: DashboardModel["composition_status"] }) {
  const cls = status === "invalid" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700";
  const Icon = status === "invalid" ? XCircle : CheckCircle2;
  return (
    <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${cls}`}>
      <Icon size={12} /> {status}
    </span>
  );
}
