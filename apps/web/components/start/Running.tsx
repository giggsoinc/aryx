"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import type { IngestQuestion } from "@/lib/types";
import { StepShell, ExampleBox } from "./StepShell";
import { Pipeline, PIPELINE_STEPS } from "./Pipeline";

interface Props {
  workspaceId: number;
  onDone: () => void;
  onSkip: () => void;
}

const POLL_MS = 6_000;
const STEP_DURATION_MS = 3_000;

/** Screen 5 — live progress through the pipeline + HITL inline.
 *  V1: the wizard starts a "demo" cadence — backend ingest fires via the
 *  Streamlit ingest flow today, so this screen polls entity counts and
 *  pending questions, and advances visual progress while waiting. */
export function Running({ workspaceId, onDone, onSkip }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [doneIndices, setDoneIndices] = useState<number[]>([]);
  const [questions, setQuestions] = useState<IngestQuestion[]>([]);

  useEffect(() => {
    if (activeIndex >= PIPELINE_STEPS.length - 1) return;
    const t = setTimeout(() => {
      setDoneIndices((d) => [...d, activeIndex]);
      setActiveIndex((i) => i + 1);
    }, STEP_DURATION_MS);
    return () => clearTimeout(t);
  }, [activeIndex]);

  const refresh = useCallback(async () => {
    try {
      const qs = await api.getIngestQuestions(workspaceId, "pending");
      setQuestions(qs);
    } catch {
      /* ignore */
    }
  }, [workspaceId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const answer = async (q: IngestQuestion, value: string) => {
    try {
      await api.answerIngestQuestion(q.id, value, "wizard");
    } finally {
      refresh();
    }
  };

  const finished = activeIndex === PIPELINE_STEPS.length - 1;

  return (
    <StepShell progress={85}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Aryx is reading your data…
      </h1>
      <p className="mt-3 max-w-lg text-center text-[14px] text-subtle">
        You can leave this open or come back later. When Aryx isn't sure, it'll
        ask you here.
      </p>

      <div className="mt-8 w-full">
        <Pipeline activeIndex={activeIndex} doneIndices={doneIndices} />
      </div>

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
