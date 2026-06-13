"use client";

import { ArrowRight } from "lucide-react";
import { StepShell } from "./StepShell";

interface Props {
  onStart: () => void;
}

const STEPS = [
  { n: 1, t: "You tell Aryx what you want to figure out",
    d: "2–5 goals or questions. That's the brief." },
  { n: 2, t: "You point Aryx at your data",
    d: "Database, files, APIs — whatever you have." },
  { n: 3, t: "Aryx proposes the model, you approve",
    d: "Records get deduped, things get linked into a map. You stay in the loop on anything ambiguous." },
  { n: 4, t: "You ask, Aryx answers",
    d: "Plain English questions. Every answer cites the records behind it." },
];

/** Screen 0 — intro / what Aryx is. Plain headline + ontology positioning. */
export function Intro({ onStart }: Props) {
  return (
    <StepShell>
      <h1 className="max-w-2xl text-center font-display text-[2.4rem] leading-tight text-navy-900">
        Aryx connects your data from a business&nbsp;thinking view.
      </h1>
      <p className="mt-5 max-w-xl text-center text-[15px] italic leading-relaxed text-steel-600">
        A discovery-driven knowledge graph built on auto-discovered ontology
        frameworks. The structure emerges from your data and your goals,
        instead of being designed in advance.
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
      <p className="mt-3 text-[12px] text-subtle">Takes about 3 minutes.</p>
    </StepShell>
  );
}
