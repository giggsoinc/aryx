"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Loader2, RefreshCw, RotateCcw } from "lucide-react";
import { Header } from "@/components/brand/Header";
import { SystemStatus } from "@/components/jobs/SystemStatus";
import { WorkspaceOverview } from "@/components/jobs/WorkspaceOverview";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace";

type Job = Awaited<ReturnType<typeof api.listJobs>>[number];

const TERMINAL = new Set(["complete", "failed", "cancelled"]);

/** Observe — full-page ops truth: every job, every workspace's counts, and
 *  what is physically stored in Postgres + FalkorDB right now. */
export default function ObservePage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setJobs(await api.listJobs(workspaceId));
    } catch { /* panel shows empty */ } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const terminalCount = jobs.filter((j) => TERMINAL.has(j.status)).length;

  const resume = async (jobId: string) => {
    setBusyId(jobId);
    try {
      await api.resumeJobRun(jobId);
      await refresh();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Resume failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-4xl px-6 pb-10 pt-6">
          <div className="mb-5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity size={20} className="text-steel-600" />
              <div>
                <h1 className="font-display text-2xl font-bold text-navy-900">Observe</h1>
                <p className="text-[13px] text-subtle">
                  Jobs, workspace vitals, and what is physically stored on this server.
                </p>
              </div>
            </div>
            <button
              type="button" onClick={refresh} disabled={loading}
              className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-navy-100 bg-white px-3 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-navy-50 disabled:opacity-50"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Refresh
            </button>
          </div>

          <div className="mb-4 rounded-xl border border-navy-100 bg-white p-3 text-[12px] text-navy-800 shadow-soft">
            <b>Why a job looks stuck:</b> Resolve on ~900 bank rows can take many minutes.
            Progress shows “still working” heartbeats. If a job false-failed with “no checkpoint”,
            use <b>Resume from checkpoint</b> when <code className="text-[11px]">run_id</code> is set;
            otherwise re-upload. Stale timeout is 30 minutes without any heartbeat.
          </div>

          {/* Jobs for the active workspace */}
          <div className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
              Ingest jobs — active workspace
            </div>
            {jobs.length === 0 ? (
              <p className="text-[12px] text-subtle">No jobs yet in this workspace.</p>
            ) : (
              <ul className="divide-y divide-navy-100/70">
                {jobs.map((j) => {
                  const canResume =
                    (j.status === "failed" || j.status === "cancelled")
                    && j.run_id != null;
                  return (
                    <li key={j.job_id} className="flex flex-col gap-1 py-2 text-[12px] sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                      <span className="min-w-0 flex-1 truncate text-navy-800">
                        {j.source_dataset || j.source_system}
                        <span className="ml-2 font-mono text-[10px] text-subtle">{j.job_id.slice(0, 8)}</span>
                        {j.run_id != null && (
                          <span className="ml-2 font-mono text-[10px] text-steel-600">
                            run {j.run_id}
                          </span>
                        )}
                      </span>
                      <span className="max-w-[280px] truncate text-subtle">{j.error || j.detail || j.stage || ""}</span>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                          j.status === "complete" ? "bg-emerald-50 text-emerald-700"
                            : j.status === "failed" || j.status === "cancelled" ? "bg-rose-50 text-rose-700"
                            : "bg-navy-50 text-navy-700",
                        )}>
                          {j.status}{j.pct != null && !TERMINAL.has(j.status) ? ` · ${j.pct}%` : ""}
                        </span>
                        {canResume && (
                          <button
                            type="button"
                            disabled={busyId === j.job_id}
                            onClick={() => resume(j.job_id)}
                            className="focus-ring inline-flex items-center gap-1 rounded-lg bg-navy-800 px-2 py-1 text-[10px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
                          >
                            {busyId === j.job_id
                              ? <Loader2 size={10} className="animate-spin" />
                              : <RotateCcw size={10} />}
                            Resume
                          </button>
                        )}
                        {!canResume && (j.status === "failed" || j.status === "cancelled") && (
                          <Link href="/start" className="text-[10px] font-semibold text-steel-600 underline">
                            Re-upload
                          </Link>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* All workspaces + physical storage truth (both self-refresh) */}
          <div className="mt-4 rounded-xl border border-navy-100 bg-white px-4 pb-1 pt-1 shadow-soft">
            <WorkspaceOverview refreshKey={terminalCount} />
          </div>
          <div className="mt-4 rounded-xl border border-navy-100 bg-white shadow-soft">
            <SystemStatus refreshKey={terminalCount} />
          </div>
        </div>
      </main>
    </div>
  );
}
