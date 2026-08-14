"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export interface ChainJobState {
  jobId: string;
  status: string;
  stage: string | null;
  pct: number | null;
  detail: string | null;
  error: string | null;
}

const POLL_MS = 3_000;
const TERMINAL = new Set(["complete", "failed", "blocked", "cancelled"]);

/** Polls one specific auto-chain job (see aryx.pipeline.auto_chain — the
 *  zero-click Brief -> Intent -> Planner -> Execution -> Dashboard chain)
 *  until it reaches a terminal state. Modeled on the Onboard wizard's
 *  Running.tsx tick() loop, scoped to a single job_id. */
export function useChainJob(jobId: string | null): ChainJobState | null {
  const [state, setState] = useState<ChainJobState | null>(null);

  useEffect(() => {
    if (!jobId) { setState(null); return; }
    let cancelled = false;
    const tick = async () => {
      try {
        const j = await api.getJob(jobId);
        if (cancelled) return;
        setState({
          jobId, status: j.status, stage: j.stage, pct: j.pct,
          detail: j.detail, error: j.error,
        });
        if (TERMINAL.has(j.status)) return;
        setTimeout(tick, POLL_MS);
      } catch {
        if (!cancelled) setTimeout(tick, POLL_MS);
      }
    };
    tick();
    return () => { cancelled = true; };
  }, [jobId]);

  return state;
}
