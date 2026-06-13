"use client";

import { CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export type PipelineStep = {
  key: string;
  ico: string;
  title: string;
  desc: string;
  eg?: string;
};

export const PIPELINE_STEPS: PipelineStep[] = [
  { key: "read", ico: "📥", title: "Read",
    desc: "Stream records from every source — one at a time.",
    eg: "e.g. 1,200 customer rows + 47 PDFs" },
  { key: "tag", ico: "🏷", title: "Tag fields",
    desc: "Recognise what each field means.",
    eg: "e.g. cust_em → email_address" },
  { key: "dedupe", ico: "🧩", title: "Dedupe",
    desc: "Find the same record across sources.",
    eg: "e.g. \"Acme Corp\" + \"Acme Corporation\" → one" },
  { key: "link", ico: "🔗", title: "Link",
    desc: "Figure out how things relate.",
    eg: "e.g. T-1043 opened_by Acme" },
  { key: "map", ico: "🗺", title: "Map",
    desc: "Build the queryable graph and the canvas.",
    eg: "e.g. 4 kinds, 1,847 records, 47k connections" },
  { key: "ready", ico: "💬", title: "Ready",
    desc: "Ask anything in plain English.",
    eg: "e.g. \"Which agents resolve network tickets fastest?\"" },
];

interface PipelineProps {
  /** Optional: index of the currently-running step. Steps before it render
   *  as done, after as upcoming. -1 (default) = all neutral / preview mode. */
  activeIndex?: number;
  doneIndices?: number[];
}

/** Under-the-covers pipeline visualization. Used as a preview screen,
 *  and reused on the running screen with live progress markers. */
export function Pipeline({ activeIndex = -1, doneIndices = [] }: PipelineProps) {
  return (
    <div className="flex w-full max-w-5xl items-stretch gap-1 overflow-x-auto px-1 pb-2">
      {PIPELINE_STEPS.map((s, i) => {
        const done = doneIndices.includes(i);
        const active = i === activeIndex;
        return (
          <div key={s.key} className="flex items-stretch">
            <div
              className={cn(
                "min-w-[150px] flex-1 rounded-2xl border bg-white px-3 py-4 text-center shadow-soft",
                done && "border-emerald-200 bg-emerald-50/40",
                active && "border-steel-500 shadow-glow",
                !done && !active && "border-navy-100",
              )}
            >
              <div
                className={cn(
                  "mx-auto flex size-10 items-center justify-center rounded-xl text-[20px]",
                  done ? "bg-emerald-100 text-emerald-700"
                       : active ? "bg-steel-500/10 text-steel-600"
                                : "bg-navy-50 text-navy-700",
                )}
              >
                {done ? <CheckCircle2 size={18} /> :
                  active ? <Loader2 size={18} className="animate-spin" /> :
                            s.ico}
              </div>
              <div className="mt-2 text-[12.5px] font-bold tracking-wide text-navy-900">
                {s.title}
              </div>
              <div className="mt-1 text-[11px] leading-snug text-subtle">
                {s.desc}
              </div>
              {s.eg && (
                <div className="mt-2 rounded-md bg-navy-50 px-1.5 py-1 font-mono text-[10px] leading-snug text-navy-700">
                  {s.eg}
                </div>
              )}
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <span className="flex items-center px-1 text-navy-300">›</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
