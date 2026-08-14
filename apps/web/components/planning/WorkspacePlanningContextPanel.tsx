"use client";

import { useEffect, useState } from "react";
import { Layers, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { PlanningContext } from "@/lib/types";

interface Props {
  workspaceId: number;
}

const STATUS_CLS: Record<string, string> = {
  complete: "bg-emerald-100 text-emerald-700",
  incomplete: "bg-amber-100 text-amber-700",
  blocked: "bg-red-100 text-red-700",
};

/** C07 (workspace scope) — the merged planning context spanning EVERY
 *  dataset in the workspace. Columns are grouped per dataset, never
 *  flattened: the same column name (e.g. 'model') often means something
 *  different in different files, so merging by name would be ambiguous. */
export function WorkspacePlanningContextPanel({ workspaceId }: Props) {
  const [ctx, setCtx] = useState<PlanningContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = () => {
    api.getWorkspacePlanningContext(workspaceId)
      .then(setCtx).catch(() => setCtx(null)).finally(() => setLoading(false));
  };
  // Live-refresh: C07 computes in the background once intent (C01) is valid
  // and at least one dataset is ingested, so poll instead of requiring the
  // manual Refresh click.
  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [workspaceId]);

  const refresh = async () => {
    setRunning(true);
    try {
      const res = await api.runWorkspacePlanningContext(workspaceId);
      setCtx(res);
    } catch {
      /* no profiled datasets yet, etc. */
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers size={18} className="text-navy-500" />
            <h2 className="text-lg font-semibold text-navy-900">Workspace Planning Context</h2>
            {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
          </div>
          <button onClick={refresh} disabled={running}
                  className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-navy-200 px-3 py-1.5 text-sm text-navy-700 hover:bg-navy-50 disabled:opacity-60">
            {running ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Refresh
          </button>
        </div>
        <p className="mt-1 text-sm text-navy-500">
          One merged context spanning every dataset in this workspace —
          columns stay grouped per dataset (never flattened), so a KPI can
          never accidentally borrow a same-named column from the wrong file.
        </p>

        {!ctx && !loading && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            No workspace context yet — ingest at least one dataset and submit intent
            (C01); this appears automatically once both are done.
          </div>
        )}

        {ctx && (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLS[ctx.context_status] ?? ""}`}>
                {ctx.context_status}
              </span>
              <span className="text-navy-500">
                {String(ctx.completeness.dataset_count ?? ctx.datasets.length)} datasets ·{" "}
                {String(ctx.completeness.columns_approved ?? "")} approved columns ·{" "}
                {ctx.approved_graph_paths.length} graph paths
              </span>
            </div>

            <div className="mt-4 max-h-96 space-y-2 overflow-y-auto">
              {ctx.datasets.map((d) => (
                <div key={d.dataset_id} className="rounded-lg border border-navy-100 p-3">
                  <div className="mb-1 flex items-center gap-2 text-sm font-medium text-navy-800">
                    {d.dataset_id}
                    <span className="text-xs font-normal text-navy-400">{d.dataset_version}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {d.approved_columns.map((c) => (
                      <span key={c.name} className="rounded bg-navy-50 px-1.5 py-0.5 text-xs text-navy-700">
                        {c.name} <span className="text-navy-400">· {c.type}</span>
                      </span>
                    ))}
                    {d.approved_columns.length === 0 && (
                      <span className="text-xs text-navy-400">No analytically usable columns.</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {ctx.warnings.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">
                {ctx.warnings.map((w, i) => (
                  <span key={i} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">{w}</span>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
