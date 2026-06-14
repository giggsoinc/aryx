"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Activity, CheckCircle2, AlertTriangle, Loader2, X,
  ChevronDown, ChevronRight,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/cn";

const POLL_MS = 5_000;

type JobRow = Awaited<ReturnType<typeof api.listJobs>>[number];

const RUNNING = new Set(["queued", "running", "pending", "in_progress"]);

/** Header chip + dockable side panel for ingest jobs.
 *  Auto-opens on / and /model whenever any job is running so the user
 *  doesn't have to know to click. No backdrop — the panel coexists with
 *  the page so they can keep working. */
export function JobsBadge() {
  const { workspaceId } = useWorkspace();
  const pathname = usePathname();
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

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

  // Auto-open on Ask + Model when something is running and user hasn't
  // dismissed the panel for this session.
  const running = jobs.filter((j) => RUNNING.has(j.status)).length;
  const onAskOrModel = pathname === "/" || pathname?.startsWith("/model");
  useEffect(() => {
    if (running > 0 && onAskOrModel && !dismissed) setOpen(true);
    if (running === 0) setDismissed(false);
  }, [running, onAskOrModel, dismissed]);

  if (jobs.length === 0) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
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
      <JobsPanel
        open={open}
        jobs={jobs}
        onClose={() => { setOpen(false); setDismissed(true); }}
        onRefresh={refresh}
      />
    </>
  );
}

interface PanelProps {
  open: boolean;
  jobs: JobRow[];
  onClose: () => void;
  onRefresh: () => void;
}

/** Docked side panel. No backdrop — page stays interactive. */
function JobsPanel({ open, jobs, onClose, onRefresh }: PanelProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          initial={{ x: 480, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 480, opacity: 0 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="fixed right-0 top-16 z-30 flex h-[calc(100vh-4rem)] w-[460px] flex-col border-l border-navy-100 bg-white shadow-soft"
        >
          <header className="flex items-center justify-between border-b border-navy-100 px-5 py-3">
            <div className="flex items-center gap-2">
              <Activity size={16} className="text-steel-500" />
              <h2 className="font-display text-[1.05rem] text-navy-900">
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
          <p className="border-b border-navy-100 px-5 py-2.5 text-[11px] text-subtle">
            Live status from <code className="rounded bg-navy-50 px-1 py-0.5 font-mono text-[10px] text-steel-600">/admin/jobs</code>{" "}
            · click a job for its event log.
          </p>
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <ul className="space-y-2">
              {jobs.map((j) => <JobCard key={j.job_id} job={j} />)}
            </ul>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function JobCard({ job }: { job: JobRow }) {
  const [open, setOpen] = useState(false);
  const isRunning = RUNNING.has(job.status);
  const isFailed = job.status === "failed" || !!job.error;
  const isDone = job.status === "complete";
  return (
    <li className={cn(
      "rounded-xl border bg-white shadow-soft",
      isFailed ? "border-rose-200" :
      isDone ? "border-emerald-200" : "border-navy-100",
    )}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full p-3.5 text-left focus-ring rounded-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {open ? <ChevronDown size={12} className="text-subtle" />
                    : <ChevronRight size={12} className="text-subtle" />}
              <StatusIcon running={isRunning} done={isDone} failed={isFailed} />
              <span className="truncate text-[13px] font-semibold text-navy-900">
                {job.source_dataset || "upload"}
              </span>
            </div>
            <div className="mt-1 ml-5 font-mono text-[10px] text-subtle">
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
          <div className="ml-5 mt-2.5">
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
          <div className="ml-5 mt-1.5 truncate text-[11px] text-navy-700">
            {job.detail}
          </div>
        )}
        {job.error && (
          <div className="ml-5 mt-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
            {job.error}
          </div>
        )}
      </button>
      {open && <EventLog jobId={job.job_id} live={isRunning} />}
    </li>
  );
}

function EventLog({ jobId, live }: { jobId: string; live: boolean }) {
  const [events, setEvents] = useState<{
    stage: string; pct: number; detail: string; ts: string;
  }[]>([]);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    try { setEvents(await api.getJobEvents(jobId)); }
    catch { setEvents([]); }
    finally { setLoading(false); }
  }, [jobId]);
  useEffect(() => {
    refresh();
    if (!live) return;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh, live]);

  return (
    <div className="border-t border-navy-100 bg-navy-50/40 px-4 py-3">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-subtle">
        Event log {live && "· live"}
      </div>
      {loading && events.length === 0 ? (
        <div className="text-[11px] italic text-subtle">Loading…</div>
      ) : events.length === 0 ? (
        <div className="text-[11px] italic text-subtle">
          No events yet — pipeline hasn't reported in.
        </div>
      ) : (
        <ol className="space-y-1.5 font-mono text-[10.5px] leading-snug text-navy-700">
          {events.map((e, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="shrink-0 text-subtle">
                {new Date(e.ts).toLocaleTimeString([], {
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </span>
              <span className="shrink-0 font-semibold text-steel-600">
                {e.stage}
              </span>
              <span className="shrink-0 text-navy-500">{e.pct}%</span>
              <span className="truncate text-navy-700">{e.detail}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
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
