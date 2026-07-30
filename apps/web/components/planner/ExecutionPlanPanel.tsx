"use client";

import { useEffect, useState } from "react";
import {
  Loader2, Workflow, CheckCircle2, XCircle, ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ExecutionPlan, ExecutionNode } from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** C11 — Execution Compiler. Read-only, whole-workspace scope: a spec's
 *  KPIs/analyses (even when they span several datasets) form ONE coherent
 *  DAG, so there is exactly one compiled plan per workspace — not one per
 *  dataset (see andie_planner.run._run_c11_for_spec). Compiled automatically
 *  once C08's spec clears C09/C10; no button here. */
export function ExecutionPlanPanel({ workspaceId }: Props) {
  const [plan, setPlan] = useState<ExecutionPlan | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api.getExecutionPlan(`workspace_${workspaceId}`, workspaceId)
        .then((p) => { if (alive) setPlan(p); })
        .catch(() => { if (alive) setPlan(null); })
        .finally(() => { if (alive) setLoading(false); });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => { alive = false; clearInterval(timer); };
  }, [workspaceId]);

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <Workflow size={18} className="text-navy-500" />
          <h2 className="text-lg font-semibold text-navy-900">Execution Plan</h2>
          {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
        </div>
        <p className="mt-1 text-sm text-navy-500">
          C11 compiles the whole-workspace dashboard spec into one typed,
          acyclic node graph bound to a fixed set of vetted operation
          templates — no LLM, no generated SQL/Python. Compiles automatically
          once a workspace-scope spec clears validation; nothing to run here.
        </p>

        {!loading && !plan && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            No execution plan yet — generate a "🌐 Whole workspace" dashboard
            spec above first.
          </div>
        )}

        {plan && <PlanView plan={plan} />}
      </section>
    </div>
  );
}

function PlanView({ plan }: { plan: ExecutionPlan }) {
  return (
    <div className={`mt-4 rounded-lg border p-4 ${plan.compilation_status === "rejected" ? "border-red-200 bg-red-50/30" : "border-navy-100 bg-navy-50/30"}`}>
      <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-navy-500">
        <StatusPill status={plan.compilation_status} />
        <span><b className="text-navy-800">{plan.plan_acyclic ? "acyclic" : "cyclic"}</b></span>
        <span><b className="text-navy-800">{plan.row_limit.toLocaleString()}</b> row limit</span>
        <span><b className="text-navy-800">{plan.nodes.length}</b>/{plan.node_limit} nodes</span>
        <code className="text-navy-400">{plan.execution_plan_id}</code>
      </div>

      {plan.issues.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {plan.issues.map((iss, i) => (
            <span key={i} title={iss.detail}
                  className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">
              {iss.code}{iss.node_id ? ` · ${iss.node_id}` : ""}
            </span>
          ))}
        </div>
      )}

      <div className="space-y-1.5">
        {plan.nodes.map((n) => <NodeRow key={n.node_id} node={n} />)}
      </div>
    </div>
  );
}

function NodeRow({ node }: { node: ExecutionNode }) {
  const params = Object.entries(node.parameters)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? `[${v.join(", ")}]` : String(v)}`)
    .join(", ");
  return (
    <div className="rounded-lg border border-navy-100 bg-white px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono font-medium text-navy-900">{node.node_id}</span>
        <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">{node.template}</span>
        {node.depends_on.length > 0 && (
          <span className="flex items-center gap-1 text-navy-400">
            <ArrowRight size={11} />
            {node.depends_on.join(", ")}
          </span>
        )}
      </div>
      {params && <div className="mt-1 font-mono text-navy-500">{params}</div>}
    </div>
  );
}

function StatusPill({ status }: { status: ExecutionPlan["compilation_status"] }) {
  const cls = status === "rejected" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700";
  return (
    <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status === "rejected" ? <XCircle size={12} /> : <CheckCircle2 size={12} />}
      {status}
    </span>
  );
}
