"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import type { IngestQuestion } from "@/lib/types";
import { StepShell, ExampleBox } from "./StepShell";
import { Pipeline, PIPELINE_STEPS } from "./Pipeline";

interface Props {
  workspaceId: number;
  /** Job id returned by the upload / connect step. When null, no real
   *  job to poll — we show a generic "running in background" message. */
  jobId: string | null;
  onDone: () => void;
  onSkip: () => void;
}

const JOB_POLL_MS = 3_000;
const QUESTIONS_POLL_MS = 8_000;

/** Map backend stage names to the visual pipeline index. The pipeline
 *  is the user-facing story: read → tag → dedupe → link → map → ready.
 *  Pipeline stages on the backend may be: extract / land / tag / map /
 *  resolve / relate / project / done. */
const STAGE_TO_INDEX: Record<string, number> = {
  extract: 0, read: 0,
  land: 0, landed: 0,
  tag: 1, tagging: 1,
  map: 1, mapping: 1, "map-fields": 1,
  resolve: 2, dedupe: 2, cluster: 2,
  relate: 3, link: 3, "fk-link": 3,
  project: 4,
  done: 5, complete: 5, ready: 5,
};

function stageIndex(stage: string | null): number {
  if (!stage) return 0;
  const key = stage.toLowerCase().trim();
  if (key in STAGE_TO_INDEX) return STAGE_TO_INDEX[key];
  // Loose match: any stage containing one of the known tokens.
  for (const [k, v] of Object.entries(STAGE_TO_INDEX)) {
    if (key.includes(k)) return v;
  }
  return 0;
}

/** Screen 5 — REAL pipeline progress driven by /admin/jobs/{job_id}.
 *  When job is null (e.g. user only set up a brief), polls HITL only. */
export function Running({ workspaceId, jobId, onDone, onSkip }: Props) {
  const [stage, setStage] = useState<string | null>(null);
  const [pct, setPct] = useState<number>(0);
  const [detail, setDetail] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string>("queued");
  const [error, setError] = useState<string | null>(null);
  const [questions, setQuestions] = useState<IngestQuestion[]>([]);

  // Poll the job — real backend state.
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const j = await api.getJob(jobId);
        if (cancelled) return;
        setStage(j.stage);
        setPct(j.pct ?? 0);
        setDetail(j.detail);
        setJobStatus(j.status);
        setError(j.error);
        if (j.status === "complete" || j.status === "failed") return;
        setTimeout(tick, JOB_POLL_MS);
      } catch {
        if (!cancelled) setTimeout(tick, JOB_POLL_MS);
      }
    };
    tick();
    return () => { cancelled = true; };
  }, [jobId]);

  // Poll HITL queue independently.
  const refreshQuestions = useCallback(async () => {
    try {
      setQuestions(await api.getIngestQuestions(workspaceId, "pending"));
    } catch { /* ignore */ }
  }, [workspaceId]);

  useEffect(() => {
    refreshQuestions();
    const t = setInterval(refreshQuestions, QUESTIONS_POLL_MS);
    return () => clearInterval(t);
  }, [refreshQuestions]);

  const answer = async (q: IngestQuestion, value: string) => {
    try {
      await api.answerIngestQuestion(q.id, value, "wizard");
    } finally {
      refreshQuestions();
    }
  };

  const active = stageIndex(stage);
  const done = Array.from({ length: active }, (_, i) => i);
  const finished = jobStatus === "complete" || (!jobId && questions.length === 0
    && active >= PIPELINE_STEPS.length - 1);

  return (
    <StepShell progress={85}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Aryx is reading your data…
      </h1>
      <p className="mt-3 max-w-lg text-center text-[14px] text-subtle">
        {jobId
          ? `Real job state — polling /admin/jobs/${jobId.slice(0, 8)}… every ${JOB_POLL_MS / 1000}s.`
          : "No active ingest job. Open Observability or come back later."}
      </p>

      <div className="mt-8 w-full">
        <Pipeline activeIndex={finished ? PIPELINE_STEPS.length - 1 : active}
                   doneIndices={finished ? [0, 1, 2, 3, 4] : done} />
      </div>

      {jobId && (
        <div className="mt-4 w-full max-w-2xl rounded-xl border border-navy-100 bg-white px-4 py-3">
          <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-subtle">
            <span>Stage</span>
            <span className="font-mono text-navy-700">
              {stage || "queued"} · {pct}% · {jobStatus}
            </span>
          </div>
          {detail && (
            <div className="mt-1 truncate text-[12px] text-navy-700">
              {detail}
            </div>
          )}
          {error && (
            <div className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-[11px] text-rose-700">
              {error}
            </div>
          )}
        </div>
      )}

      {questions.length > 0 && (
        <section className="mt-6 w-full max-w-2xl space-y-3">
          {questions.slice(0, 3).map((q) => (
            <QuestionCard key={q.id} q={q}
                           onAnswer={(v) => answer(q, v)} />
          ))}
        </section>
      )}

      {questions.length === 0 && !finished && (
        <ExampleBox label="When Aryx is unsure">
          You'll see a question here like{" "}
          <em>"I see Customer and Account — same kind of thing or different?"</em>
          {" "}with one-tap answers. Your answer unblocks the pipeline instantly.
        </ExampleBox>
      )}

      <div className="mt-8 flex gap-3">
        <button
          onClick={onSkip}
          className="focus-ring text-[12px] text-subtle hover:text-navy-700"
        >
          Run in the background
        </button>
        {finished && (
          <button
            onClick={onDone}
            className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-navy-700"
          >
            See what I learned <ArrowRight size={14} />
          </button>
        )}
      </div>
    </StepShell>
  );
}

function QuestionCard({
  q, onAnswer,
}: { q: IngestQuestion; onAnswer: (v: string) => void }) {
  const opts = q.options && q.options.length > 0
    ? q.options : ["Same", "Different", "Skip for now"];
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4 shadow-soft">
      <div className="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-800">
        A question for you
      </div>
      <div className="mt-2 text-[14px] text-navy-900">{q.prompt}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {opts.map((o) => (
          <button
            key={o}
            onClick={() => onAnswer(o)}
            className="focus-ring rounded-full border border-amber-300 bg-white px-3.5 py-1.5 text-[12px] font-medium text-amber-900 hover:bg-amber-100"
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}
