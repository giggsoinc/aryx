"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity, CheckCircle2, AlertTriangle, Loader2, X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";

const POLL_MS = 5_000;

type JobRow = Awaited<ReturnType<typeof api.listJobs>>[number];

const RUNNING = new Set(["queued", "running", "pending", "in_progress"]);

/** Header chip that surfaces ingest jobs for the active workspace.
 *  - Spinner + count chip when any job is running.
 *  - Click to open a drawer listing recent jobs with stage / pct / status. */
export function JobsBadge() {
  const { workspaceId } = useWorkspace();
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setJobs(await api.listJobs(workspaceId));
    } catch {
      setJobs([]);
    }
  }, [workspaceId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const running = jobs.filter((j) => RUNNING.has(j.status)).length;
  const hasAny = jobs.length > 0;
  if (!hasAny) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={running > 0
          ? `${running} ingest job${running === 1 ? "" : "s"} running`
          : "Recent ingest jobs"}
        className="focus-ring relative inline-flex size-9 items-center justify-center rounded-lg text-navy-600 transition-colors hover:bg-navy-50 hover:text-navy-900"
      >
        {running > 0
          ? <Loader2 size={16} className="animate-spin text-steel-500" />
          : <Activity size={16} />}
        {running > 0 && (
          <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-steel-500 px-1 text-[10px] font-semibold text-white shadow-sm">
            {running}
          </span>
        )}
      </button>
      <JobsDrawer
        open={open}
        jobs={jobs}
        onClose={() => setOpen(false)}
        onRefresh={refresh}
      />
    </>
  );
}

interface DrawerProps {
  open: boolean;
  jobs: JobRow[];
  onClose: () => void;
  onRefresh: () => void;
}

function JobsDrawer({ open, jobs, onClose, onRefresh }: DrawerProps) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-30 bg-navy-950/20 backdrop-blur-sm"
          />
          <motion.aside
            initial={{ x: 480, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 480, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 z-40 flex h-screen w-[460px] flex-col border-l border-navy-100 bg-white shadow-soft"
          >
            <header className="flex items-center justify-between border-b border-navy-100 px-5 py-4">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-steel-500" />
                <h2 className="font-display text-[1.1rem] text-navy-900">
                  Ingest jobs
                </h2>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={onRefresh}
                  className="focus-ring rounded-lg px-2 py-1 text-[11px] font-medium text-subtle hover:bg-navy-50"
                >
                  Refresh
                </button>
                <button
                  onClick={onClose}
                  className="focus-ring rounded-lg p-1 text-subtle hover:bg-navy-50"
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </div>
            </header>
            <p className="border-b border-navy-100 px-5 py-3 text-[12px] text-subtle">
              Live status from <code className="rounded bg-navy-50 px-1.5 py-0.5 font-mono text-[11px] text-steel-600">/admin/jobs</code>{" "}
              for this workspace.
            </p>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {jobs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-navy-200 px-5 py-10 text-center text-[13px] text-subtle">
                  No ingest jobs for this workspace yet.
                </div>
              ) : (
                <ul className="space-y-3">
                  {jobs.map((j) => <JobCard key={j.job_id} job={j} />)}
                </ul>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function JobCard({ job }: { job: JobRow }) {
  const isRunning = RUNNING.has(job.status);
  const isFailed = job.status === "failed" || !!job.error;
  const isDone = job.status === "complete";
  return (
    <li className={cn(
      "rounded-xl border bg-white p-4 shadow-soft",
      isFailed ? "border-rose-200" :
      isDone ? "border-emerald-200" : "border-navy-100",
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <StatusIcon running={isRunning} done={isDone} failed={isFailed} />
            <span className="truncate text-[13px] font-semibold text-navy-900">
              {job.source_dataset || "upload"}
            </span>
          </div>
          <div className="mt-1 font-mono text-[10px] text-subtle">
            {job.source_system} · {job.job_id.slice(0, 12)}…
          </div>
        </div>
        <span className={cn(
          "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
          isRunning && "bg-steel-500/15 text-steel-600",
          isDone && "bg-emerald-50 text-emerald-700",
          isFailed && "bg-rose-50 text-rose-700",
          !isRunning && !isDone && !isFailed && "bg-navy-50 text-navy-700",
        )}>
          {job.status}
        </span>
      </div>

      {(job.stage || job.pct !== null) && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-[11px] text-subtle">
            <span className="font-mono">{job.stage || "queued"}</span>
            <span className="font-mono">{job.pct ?? 0}%</span>
          </div>
          <div className="mt-1 h-1.5 w-full rounded-full bg-navy-100">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                isFailed ? "bg-rose-400" : "bg-steel-500",
              )}
              style={{ width: `${Math.min(job.pct ?? 0, 100)}%` }}
            />
          </div>
        </div>
      )}

      {job.detail && (
        <div className="mt-2 truncate text-[11px] text-navy-700">
          {job.detail}
        </div>
      )}
      {job.error && (
        <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
          {job.error}
        </div>
      )}
    </li>
  );
}

function StatusIcon({
  running, done, failed,
}: { running: boolean; done: boolean; failed: boolean }) {
  if (failed) return <AlertTriangle size={13} className="text-rose-500" />;
  if (done) return <CheckCircle2 size={13} className="text-emerald-500" />;
  if (running) return <Loader2 size={13} className="animate-spin text-steel-500" />;
  return <Activity size={13} className="text-subtle" />;
}
