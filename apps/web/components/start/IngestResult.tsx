"use client";

import { useCallback, useState } from "react";
import {
  RefreshCw, Loader2, ChevronDown, ChevronRight,
  FileStack, Sparkles, GitMerge, AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

interface Props {
  jobId: string;
  workspaceId: number;
}

interface Block<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useBlock<T>(fetcher: () => Promise<T>) {
  const [state, setState] = useState<Block<T>>({ data: null, loading: false, error: null });
  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fetcher();
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState({ data: null, loading: false, error: String(e) });
    }
  }, [fetcher]);
  return { ...state, load };
}

function BlockHeader({
  icon, label, loading, onRefresh,
}: {
  icon: React.ReactNode;
  label: string;
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">
        {icon}
        {label}
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        className="focus-ring inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] text-steel-600 hover:bg-navy-50 disabled:opacity-40"
      >
        {loading
          ? <Loader2 size={10} className="animate-spin" />
          : <RefreshCw size={10} />}
        Refresh
      </button>
    </div>
  );
}

/** Post-ingest result card — 3 independently refreshable blocks + on-demand diagnosis. */
export function IngestResult({ jobId, workspaceId }: Props) {
  // Block A — Records processed (from job events: look for max landed detail)
  const jobBlock = useBlock(useCallback(
    () => api.getJobEvents(jobId), [jobId],
  ));

  // Block B — What we discovered (entity types + counts)
  const summaryBlock = useBlock(useCallback(
    () => api.dataSummary(workspaceId), [workspaceId],
  ));

  // Block C — Connections mapped (from workspace overview single-workspace view)
  const overviewBlock = useBlock(useCallback(async () => {
    const all = await api.workspaceOverview();
    return all.find((w) => w.id === workspaceId) ?? null;
  }, [workspaceId]));

  // Diagnosis (on demand) — reuses jobBlock; no second fetch.
  const [diagOpen, setDiagOpen] = useState(false);

  const toggleDiag = () => {
    if (!diagOpen && !jobBlock.data) jobBlock.load();
    setDiagOpen((v) => !v);
  };

  // Derive a landed-records count from the event detail text.
  const landedCount = (() => {
    if (!jobBlock.data) return null;
    for (const e of jobBlock.data) {
      const m = e.detail?.match(/(\d[\d,]*)\s+(record|row|file)/i);
      if (m) return parseInt(m[1].replace(/,/g, ""), 10);
    }
    return null;
  })();

  return (
    <div className="mt-6 w-full max-w-2xl space-y-3">
      {/* Block A — Records */}
      <div className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
        <BlockHeader
          icon={<FileStack size={12} />}
          label="Records processed"
          loading={jobBlock.loading}
          onRefresh={jobBlock.load}
        />
        <div className="mt-3">
          {jobBlock.data == null && !jobBlock.loading ? (
            <button
              type="button"
              onClick={jobBlock.load}
              className="text-[12px] text-steel-600 underline underline-offset-2"
            >
              Load
            </button>
          ) : jobBlock.loading ? (
            <Loader2 size={14} className="animate-spin text-subtle" />
          ) : landedCount != null ? (
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-semibold text-navy-900">
                {landedCount.toLocaleString()}
              </span>
              <span className="text-[13px] text-subtle">source records read</span>
            </div>
          ) : (
            <span className="text-[12px] text-subtle">
              Run complete — check the event log for record counts.
            </span>
          )}
        </div>
      </div>

      {/* Block B — Entities */}
      <div className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
        <BlockHeader
          icon={<Sparkles size={12} />}
          label="What we discovered"
          loading={summaryBlock.loading}
          onRefresh={summaryBlock.load}
        />
        <div className="mt-3">
          {summaryBlock.data == null && !summaryBlock.loading ? (
            <button
              type="button"
              onClick={summaryBlock.load}
              className="text-[12px] text-steel-600 underline underline-offset-2"
            >
              Load
            </button>
          ) : summaryBlock.loading ? (
            <Loader2 size={14} className="animate-spin text-subtle" />
          ) : summaryBlock.data ? (
            <div className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="font-display text-3xl font-semibold text-navy-900">
                  {summaryBlock.data.total_entities.toLocaleString()}
                </span>
                <span className="text-[13px] text-subtle">
                  unique entities across {summaryBlock.data.type_count} types
                </span>
              </div>
              {summaryBlock.data.duplicates_merged > 0 && (
                <p className="text-[11px] text-subtle">
                  {summaryBlock.data.duplicates_merged.toLocaleString()} duplicates merged
                </p>
              )}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {summaryBlock.data.types.slice(0, 6).map((t) => (
                  <span
                    key={t.name}
                    className="rounded-full border border-navy-100 bg-navy-50 px-2.5 py-0.5 text-[11px] font-medium text-navy-700"
                  >
                    {t.name} · {t.count}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <span className="text-[12px] text-rose-600">{summaryBlock.error}</span>
          )}
        </div>
      </div>

      {/* Block C — Relationships */}
      <div className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
        <BlockHeader
          icon={<GitMerge size={12} />}
          label="Connections mapped"
          loading={overviewBlock.loading}
          onRefresh={overviewBlock.load}
        />
        <div className="mt-3">
          {overviewBlock.data == null && !overviewBlock.loading ? (
            <button
              type="button"
              onClick={overviewBlock.load}
              className="text-[12px] text-steel-600 underline underline-offset-2"
            >
              Load
            </button>
          ) : overviewBlock.loading ? (
            <Loader2 size={14} className="animate-spin text-subtle" />
          ) : overviewBlock.data ? (
            <div className="flex items-baseline gap-2">
              <span className="font-display text-3xl font-semibold text-navy-900">
                {overviewBlock.data.relationships.toLocaleString()}
              </span>
              <span className="text-[13px] text-subtle">relationships discovered</span>
            </div>
          ) : (
            <span className="text-[12px] text-rose-600">{overviewBlock.error}</span>
          )}
        </div>
      </div>

      {/* Diagnosis — on demand only */}
      <div className="rounded-xl border border-navy-100 bg-white shadow-soft">
        <button
          type="button"
          onClick={toggleDiag}
          className="focus-ring flex w-full items-center gap-2 rounded-xl px-4 py-3 text-left text-[11px] font-medium text-subtle hover:bg-navy-50"
        >
          {diagOpen
            ? <ChevronDown size={12} />
            : <ChevronRight size={12} />}
          <AlertTriangle size={12} className="text-amber-500" />
          Diagnose this run
          <span className="ml-auto text-[10px] opacity-60">
            {diagOpen ? "hide" : "show event log"}
          </span>
        </button>
        {diagOpen && (
          <div className="border-t border-navy-100 px-4 pb-4 pt-3">
            {jobBlock.loading ? (
              <Loader2 size={13} className="animate-spin text-subtle" />
            ) : jobBlock.data && jobBlock.data.length > 0 ? (
              <ol className="space-y-1.5 font-mono text-[10.5px] leading-snug text-navy-700">
                {jobBlock.data.map((e) => (
                  <li key={`${e.stage}-${e.ts}`} className="flex items-start gap-2">
                    <span className="shrink-0 text-subtle">
                      {new Date(e.ts).toLocaleTimeString([], {
                        hour: "2-digit", minute: "2-digit", second: "2-digit",
                      })}
                    </span>
                    <span className={cn(
                      "shrink-0 font-semibold",
                      e.stage?.toLowerCase().includes("fail") ||
                      e.stage?.toLowerCase().includes("error")
                        ? "text-rose-600" : "text-steel-600",
                    )}>
                      {e.stage}
                    </span>
                    <span className="shrink-0 text-navy-400">{e.pct}%</span>
                    <span className="truncate text-navy-700">{e.detail}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-[11px] italic text-subtle">No events recorded.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

