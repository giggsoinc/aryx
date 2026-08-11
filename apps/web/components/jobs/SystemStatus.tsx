"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

type Status = Awaited<ReturnType<typeof api.systemStatus>>;

function Dot({ ok }: { ok: boolean | undefined }) {
  return (
    <span className={cn(
      "inline-block size-2 shrink-0 rounded-full",
      ok === undefined ? "bg-navy-200" : ok ? "bg-emerald-500" : "bg-rose-500",
    )} />
  );
}

/** Physical storage truth — the aryx_stat concept in the product. Shows what
 *  is ACTUALLY stored in Postgres and projected into FalkorDB right now,
 *  straight from the stores. If a load "succeeded" but these are zero, the
 *  data did not land — no guessing. */
export function SystemStatus({ refreshKey = 0 }: { refreshKey?: number }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      setStatus(await api.systemStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "status unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  // Refresh on mount, on job transitions (refreshKey), and every 10s while
  // the panel is open — storage truth must track the job cards live.
  useEffect(() => { refresh(); }, [refresh, refreshKey]);
  useEffect(() => {
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, [refresh]);

  const graphByWs = new Map(
    (status?.falkordb.graphs ?? []).map((g) => [g.workspace_id, g]),
  );

  return (
    <div className="border-t border-navy-100 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
          Stored on this server
        </span>
        <button
          type="button" onClick={refresh} disabled={loading}
          className="focus-ring inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-steel-600 hover:bg-navy-50 disabled:opacity-40"
        >
          {loading ? <Loader2 size={9} className="animate-spin" /> : <RefreshCw size={9} />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700">
          {error}
        </div>
      )}

      {status && (
        <div className="space-y-2 text-[11px]">
          {/* Service health line */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="flex items-center gap-1.5">
              <Dot ok={status.postgres.ok} />
              Postgres{status.postgres.db_size ? ` · ${status.postgres.db_size}` : ""}
            </span>
            <span className="flex items-center gap-1.5">
              <Dot ok={status.falkordb.ok} /> FalkorDB
            </span>
            <span className="flex items-center gap-1.5" title={status.llm.detail}>
              <Dot ok={status.llm.ok} /> {status.llm.provider || "LLM"}
              {!status.llm.ok && <span className="text-amber-700"> — {status.llm.detail}</span>}
            </span>
          </div>

          {/* Per-workspace physical counts: RDB truth vs graph projection */}
          {status.postgres.workspaces.length > 0 && (
            <table className="w-full text-left">
              <thead>
                <tr className="text-[9px] uppercase tracking-wider text-subtle">
                  <th className="py-0.5 pr-2 font-semibold">Workspace</th>
                  <th className="py-0.5 pr-2 font-semibold">Records</th>
                  <th className="py-0.5 pr-2 font-semibold">Entities</th>
                  <th className="py-0.5 pr-2 font-semibold">Links</th>
                  <th className="py-0.5 font-semibold">Graph</th>
                </tr>
              </thead>
              <tbody>
                {status.postgres.workspaces.map((w) => {
                  const g = graphByWs.get(w.id);
                  return (
                    <tr key={w.id} className="text-navy-800">
                      <td className="max-w-[110px] truncate py-0.5 pr-2" title={w.name}>{w.name}</td>
                      <td className="py-0.5 pr-2">{w.landed_records.toLocaleString()}</td>
                      <td className="py-0.5 pr-2">{w.entities.toLocaleString()}</td>
                      <td className="py-0.5 pr-2">{w.relationships.toLocaleString()}</td>
                      <td className="py-0.5">
                        {g ? `${g.nodes.toLocaleString()}n · ${g.edges.toLocaleString()}e` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {(status.postgres.doc_chunks ?? 0) > 0 && (
            <div className="text-subtle">
              Documents: {status.postgres.doc_chunks!.toLocaleString()} chunks ·{" "}
              {status.postgres.chunk_embeddings!.toLocaleString()} embeddings
            </div>
          )}
        </div>
      )}
    </div>
  );
}
