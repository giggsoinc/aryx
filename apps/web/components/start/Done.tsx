"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, Network, MessageCircle, RefreshCw, Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import type { OntologyType } from "@/lib/types";
import { StepShell } from "./StepShell";

interface Props {
  workspaceId: number;
}

const POLL_MS = 4_000;
const RUNNING_STATUSES = new Set(["queued", "running", "pending", "in_progress"]);

/** Screen 6 — what Aryx has learned so far. Auto-refreshes while any
 *  ingest job is still running so the counts catch up to reality. */
export function Done({ workspaceId }: Props) {
  const [types, setTypes] = useState<OntologyType[]>([]);
  const [entityCount, setEntityCount] = useState(0);
  const [relCount, setRelCount] = useState(0);
  const [runningJobs, setRunningJobs] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [d, jobs] = await Promise.all([
        api.getOntology(workspaceId),
        api.listJobs(workspaceId).catch(() => []),
      ]);
      setTypes(d.types || []);
      setEntityCount(d.entity_count || 0);
      setRelCount((d.relationships || []).length);
      setRunningJobs(jobs.filter((j) => RUNNING_STATUSES.has(j.status)).length);
    } catch {
      /* ignore */
    }
  }, [workspaceId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const noDataYet = types.length === 0 && entityCount === 0;
  const stillRunning = runningJobs > 0;

  return (
    <StepShell progress={100}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        {stillRunning ? "Still reading your data…" : "Here's what I learned:"}
      </h1>

      {stillRunning && (
        <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-steel-400 bg-steel-500/10 px-4 py-1.5 text-[12px] font-medium text-steel-700">
          <Loader2 size={13} className="animate-spin" />
          {runningJobs} ingest job{runningJobs === 1 ? "" : "s"} still running ·
          click the spinner in the header to see live status
        </div>
      )}

      <div className="mt-8 flex max-w-3xl flex-wrap justify-center gap-3">
        {noDataYet ? (
          <div className="rounded-2xl border border-dashed border-navy-200 bg-white px-6 py-5 text-center text-[13px] text-subtle">
            {stillRunning
              ? "Aryx is still chunking, embedding, and extracting from your sources. Counts will appear here as records land."
              : "No records read yet — give it a moment, or hit refresh."}
          </div>
        ) : (
          types.slice(0, 8).map((t) => (
            <div
              key={t.name}
              className="rounded-xl border-[1.5px] border-navy-100 bg-white px-5 py-3.5 text-center shadow-soft"
            >
              <div className="text-[14px] font-semibold text-navy-900">
                {t.name}
              </div>
              <div className="mt-1 font-mono text-[11px] text-subtle">
                {t.instance_count ?? 0} records
              </div>
            </div>
          ))
        )}
      </div>

      <div className="mt-5 flex items-center gap-3 text-[13px] text-subtle">
        <span>
          <span className="font-semibold text-navy-700">
            {entityCount.toLocaleString()}
          </span>{" "}
          records ·{" "}
          <span className="font-semibold text-navy-700">
            {relCount.toLocaleString()}
          </span>{" "}
          connections.
        </span>
        <button
          type="button"
          onClick={refresh}
          className="focus-ring inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] text-steel-600 hover:bg-navy-50"
        >
          <RefreshCw size={11} /> Refresh
        </button>
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-6 py-3 text-[15px] font-semibold text-white hover:bg-navy-700"
        >
          <MessageCircle size={15} /> Ask Aryx a question{" "}
          <ArrowRight size={15} />
        </Link>
        <Link
          href="/model"
          className="focus-ring inline-flex items-center gap-2 rounded-xl border border-navy-100 bg-white px-5 py-3 text-[14px] font-medium text-navy-700 hover:bg-navy-50"
        >
          <Network size={15} /> See the map
        </Link>
      </div>
    </StepShell>
  );
}
