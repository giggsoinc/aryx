"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Loader2, Database, Sparkles, GitMerge, Activity } from "lucide-react";
import { api } from "@/lib/api";

type WsRow = {
  id: number;
  name: string;
  entities: number;
  relationships: number;
  landed_records: number;
  running_jobs: number;
};

function Stat({ icon, value, label }: { icon: React.ReactNode; value: number; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-subtle">{icon}</span>
      <span className="text-[12px] font-semibold text-navy-900">{value.toLocaleString()}</span>
      <span className="text-[11px] text-subtle">{label}</span>
    </div>
  );
}

function WorkspaceCard({ ws, onRefresh }: { ws: WsRow; onRefresh: () => void }) {
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { await onRefresh(); } finally { setLoading(false); }
  }, [onRefresh]);

  return (
    <div className="rounded-lg border border-navy-100 bg-white p-3 shadow-soft">
      <div className="mb-2 flex items-center justify-between">
        <span className="max-w-[140px] truncate text-[12px] font-semibold text-navy-800" title={ws.name}>
          {ws.name}
        </span>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-steel-600 hover:bg-navy-50 disabled:opacity-40"
        >
          {loading
            ? <Loader2 size={9} className="animate-spin" />
            : <RefreshCw size={9} />}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        <Stat icon={<Database size={10} />} value={ws.landed_records} label="records" />
        <Stat icon={<Sparkles size={10} />} value={ws.entities} label="entities" />
        <Stat icon={<GitMerge size={10} />} value={ws.relationships} label="edges" />
        <div className="flex items-center gap-1.5">
          <span className="text-subtle"><Activity size={10} /></span>
          {ws.running_jobs > 0 ? (
            <>
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              <span className="text-[11px] font-semibold text-emerald-700">
                {ws.running_jobs} running
              </span>
            </>
          ) : (
            <span className="text-[11px] text-subtle">idle</span>
          )}
        </div>
      </div>
    </div>
  );
}

/** Per-workspace summary panel — lives inside JobsBadge's side panel below the job cards. */
export function WorkspaceOverview() {
  const [data, setData] = useState<WsRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await api.workspaceOverview();
      setData(rows);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-load on mount.
  useEffect(() => { loadAll(); }, [loadAll]);

  if (!data && !loading && !error) return null;

  return (
    <div className="mt-4 border-t border-navy-100 pt-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-subtle">
          Workspaces
        </span>
        <button
          type="button"
          onClick={loadAll}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-steel-600 hover:bg-navy-50 disabled:opacity-40"
        >
          {loading
            ? <Loader2 size={9} className="animate-spin" />
            : <RefreshCw size={9} />}
          Refresh all
        </button>
      </div>

      {error && (
        <p className="text-[11px] text-rose-600">{error}</p>
      )}

      {loading && !data && (
        <div className="flex justify-center py-3">
          <Loader2 size={14} className="animate-spin text-subtle" />
        </div>
      )}

      {data && data.length === 0 && (
        <p className="text-[11px] italic text-subtle">No workspaces yet.</p>
      )}

      {data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((ws) => (
            <WorkspaceCard key={ws.id} ws={ws} onRefresh={loadAll} />
          ))}
        </div>
      )}
    </div>
  );
}
