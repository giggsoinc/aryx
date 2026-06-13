"use client";

import { useState } from "react";
import { ArrowRight, Database, FileText, Hand } from "lucide-react";
import { cn } from "@/lib/cn";
import { StepShell, ExampleBox } from "./StepShell";

export type SourceKind = "database" | "files" | "manual";

interface Props {
  initial?: SourceKind[];
  onContinue: (picked: SourceKind[]) => void;
  onBack: () => void;
}

const CARDS: Array<{ kind: SourceKind; ico: React.ReactNode;
                      label: string; hint: string }> = [
  { kind: "database", ico: <Database size={32} />, label: "Database",
    hint: "Postgres, MySQL, Oracle" },
  { kind: "files", ico: <FileText size={32} />, label: "Files",
    hint: "PDF, CSV, Word, Excel" },
  { kind: "manual", ico: <Hand size={32} />, label: "Add by hand",
    hint: "Type records yourself" },
];

/** Screen 3 — multi-select data sources. */
export function Sources({ initial = ["database"], onContinue, onBack }: Props) {
  const [picked, setPicked] = useState<Set<SourceKind>>(new Set(initial));

  const toggle = (k: SourceKind) => {
    const next = new Set(picked);
    next.has(k) ? next.delete(k) : next.add(k);
    setPicked(next);
  };

  const list = Array.from(picked);

  return (
    <StepShell progress={50}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Where is your data?
      </h1>
      <p className="mt-3 max-w-lg text-center text-[14px] text-subtle">
        Tick any that apply — you can add more later.
      </p>

      <div className="mt-8 grid w-full max-w-2xl grid-cols-3 gap-4">
        {CARDS.map((c) => {
          const on = picked.has(c.kind);
          return (
            <button
              key={c.kind}
              type="button"
              onClick={() => toggle(c.kind)}
              className={cn(
                "focus-ring relative rounded-2xl border-[1.5px] px-5 pb-5 pt-8 text-center transition-all",
                on
                  ? "border-navy-800 bg-navy-50 shadow-glow"
                  : "border-navy-100 bg-white hover:border-steel-400",
              )}
            >
              <span
                className={cn(
                  "absolute right-2.5 top-2.5 inline-flex size-5 items-center justify-center rounded-full text-[10px] font-bold",
                  on
                    ? "bg-navy-800 text-white"
                    : "border-[1.5px] border-dashed border-navy-200 text-transparent",
                )}
              >
                ✓
              </span>
              <div className="flex justify-center text-steel-500">{c.ico}</div>
              <div className="mt-3 text-[14px] font-semibold text-navy-800">
                {c.label}
              </div>
              <div className="mt-1 text-[11px] text-subtle">{c.hint}</div>
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex w-full max-w-2xl items-center justify-between gap-3">
        <button
          onClick={onBack}
          className="focus-ring text-[12px] text-subtle hover:text-navy-700"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={() => onContinue(list)}
          disabled={list.length === 0}
          className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          Continue with {list.length} source{list.length === 1 ? "" : "s"}{" "}
          <ArrowRight size={14} />
        </button>
      </div>

      <ExampleBox label="Real setups blend sources">
        A support team picks <strong>Database</strong> (tickets and customers in
        Postgres) <em>and</em> <strong>Files</strong> (device manuals and
        resolution PDFs). Aryx reads both, finds the same device in both, and
        links them.
      </ExampleBox>
    </StepShell>
  );
}
