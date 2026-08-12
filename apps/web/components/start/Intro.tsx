"use client";

import { ArrowRight } from "lucide-react";
import { StepShell } from "./StepShell";

interface Props {
  onStart: () => void;
}

const STEPS = [
  { n: 1, t: "You point Aryx at your data first",
    d: "Files or a database — samples are enough to start." },
  { n: 2, t: "Aryx reads samples and drafts the plan",
    d: "Your Settings model (any provider) proposes the brief and the graph — merchants, types, links — not a blank form for you to invent." },
  { n: 3, t: "You approve lightly; add docs if suggested",
    d: "Correct anything off. Optional extra files sharpen the outcome." },
  { n: 4, t: "Aryx builds the graph; you ask",
    d: "Entities link with provenance. Plain-English questions with citations." },
];

/** Screen 0 — intro / data-first product story. */
export function Intro({ onStart }: Props) {
  return (
    <StepShell>
      <h1 className="max-w-2xl text-center font-display text-[2.4rem] leading-tight text-navy-900">
        Load your data. Aryx figures out the rest.
      </h1>
      <p className="mt-5 max-w-xl text-center text-[15px] italic leading-relaxed text-steel-600">
        Data first — then a smart brief and graph plan from samples.
        You stay in the loop; you don&apos;t fill six empty questions cold.
      </p>

      <section className="mt-10 w-full max-w-xl rounded-2xl bg-navy-50 p-6">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-navy-700">
          How it works
        </div>
        <ol className="mt-4 flex flex-col gap-3.5">
          {STEPS.map((s) => (
            <li key={s.n} className="flex items-start gap-3.5">
              <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg border border-navy-100 bg-white text-[12px] font-semibold text-navy-700">
                {s.n}
              </span>
              <div>
                <div className="text-[14px] font-semibold text-navy-900">
                  {s.t}
                </div>
                <div className="mt-0.5 text-[12px] text-subtle">{s.d}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <button
        type="button"
        onClick={onStart}
        className="focus-ring mt-8 inline-flex items-center gap-2 rounded-2xl bg-navy-800 px-7 py-3.5 text-[15px] font-semibold text-white hover:bg-navy-700 active:scale-[0.98]"
      >
        Get started <ArrowRight size={16} />
      </button>
      <p className="mt-3 text-[12px] text-subtle">
        About 3 minutes · model from Settings (Gemini, Ollama, …)
      </p>
    </StepShell>
  );
}
