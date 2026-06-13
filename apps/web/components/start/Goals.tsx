"use client";

import { useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Brief } from "@/lib/types";
import { StepShell, ExampleBox } from "./StepShell";

interface Props {
  workspaceId: number;
  onDrafted: (brief: Brief, goals: string) => void;
  onSkip: () => void;
}

const STARTERS = [
  "Find customers at risk of churning",
  "Predict which deals will close this quarter",
  "Spot patients overdue for follow-up",
  "See where my BOM has single-source risk",
];

const PLACEHOLDER = `Match support tickets to the right expert agent.
Spot devices likely to need RMA before they fail.
See which agents resolve network tickets fastest.
Track time-to-resolution by ticket priority.`;

/** Screen 1 — goals/objectives. Drives brief_draft. */
export function Goals({ workspaceId, onDrafted, onSkip }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const seed = text.trim();
    if (!seed) return;
    setBusy(true);
    setError(null);
    try {
      const { brief } = await api.draftBrief(workspaceId, seed);
      onDrafted(brief, seed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Draft failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <StepShell progress={20}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        What do you want Aryx to help you&nbsp;figure&nbsp;out?
      </h1>
      <p className="mt-3 max-w-lg text-center text-[14px] text-subtle">
        List 2–5 questions or goals. Plain English. The nouns become your
        data model automatically.
      </p>

      <textarea
        rows={5}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={PLACEHOLDER}
        className="focus-ring mt-8 w-full max-w-xl resize-y rounded-2xl border-[1.5px] border-navy-100 bg-white px-5 py-4 text-[15px] leading-relaxed text-ink shadow-soft placeholder:text-subtle/70 focus:border-steel-500"
      />

      {error && (
        <div className="mt-3 w-full max-w-xl rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {error}
        </div>
      )}

      <div className="mt-4 flex w-full max-w-xl items-center justify-between gap-3">
        <button
          onClick={onSkip}
          type="button"
          className="focus-ring text-[12px] text-subtle hover:text-navy-700"
        >
          Skip — I'll do this later
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={busy || !text.trim()}
          className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          {busy ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <>✨&nbsp;Continue <ArrowRight size={14} /></>
          )}
        </button>
      </div>

      <div className="mt-6 w-full max-w-xl">
        <div className="mb-2 text-[11px] text-subtle">
          Or pick a starter to adapt:
        </div>
        <div className="flex flex-wrap gap-2">
          {STARTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setText((t) => (t ? `${t}\n${s}` : s))}
              className="focus-ring rounded-full border border-navy-100 bg-white px-3.5 py-1.5 text-[12px] text-navy-700 hover:border-steel-400 hover:bg-navy-50"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <ExampleBox label="What Aryx does next">
        Your goals become the <em>aim</em> of the model and the test for whether
        it works. The nouns in your goals (tickets, customers, devices,
        agents) become the first <em>kinds of records</em> Aryx will look for.
      </ExampleBox>
    </StepShell>
  );
}
