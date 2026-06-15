"use client";

import { useState } from "react";
import { FlaskConical, Loader2, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import type { AbResult } from "@/lib/types";
import { ReasonerCard } from "./ReasonerCard";
import { ScoreCard } from "./ScoreCard";
import { VariantCard } from "./VariantCard";

const EXAMPLES = [
  "Who are our most connected customers?",
  "Which tickets are linked to overdue invoices?",
  "Summarise what this workspace knows about Acme.",
];

/** The Accuracy Lab: same model, same question, ontology on vs off. */
export function AbLab() {
  const { workspaceId } = useWorkspace();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AbResult | null>(null);

  const run = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const res = await api.labAb(text, workspaceId);
      if ("error" in res && res.error) throw new Error(res.error);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <div className="flex items-center gap-2 text-steel-600">
        <FlaskConical size={18} />
        <span className="text-[11px] font-bold uppercase tracking-[0.16em]">
          Accuracy Lab
        </span>
      </div>
      <h1 className="mt-2 font-serif text-3xl text-navy-900">
        Does the ontology actually make answers more accurate?
      </h1>
      <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-subtle">
        Ask anything about this workspace. Aryx runs the <b>same model</b> twice
        — once grounded in your knowledge graph, once with no grounding at all —
        and shows you which answer is backed by real source records.
      </p>

      <div className="mt-6 flex items-center gap-2 rounded-2xl border border-navy-100 bg-white p-2 shadow-soft">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run(q)}
          placeholder="Ask a question to compare…"
          className="focus-ring w-full rounded-xl bg-transparent px-3 py-2.5 text-[14px] text-navy-900 placeholder:text-navy-300"
        />
        <button
          type="button"
          onClick={() => run(q)}
          disabled={!q.trim() || busy}
          className="focus-ring inline-flex flex-none items-center gap-1.5 rounded-xl bg-navy-800 px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
        >
          {busy ? <Loader2 size={14} className="animate-spin" />
                : <Sparkles size={14} />}
          Run comparison
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => { setQ(ex); run(ex); }}
            disabled={busy}
            className="focus-ring rounded-full border border-navy-100 bg-white px-3 py-1.5 text-[12px] text-navy-600 hover:border-navy-200 hover:bg-navy-50 disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>

      <div className="mt-4">
        <ReasonerCard />
      </div>

      {error && (
        <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] text-rose-700">
          {error}
        </div>
      )}

      {busy && !result && (
        <div className="mt-8 flex items-center gap-2 text-[13px] text-subtle">
          <Loader2 size={15} className="animate-spin" />
          Running the same model with the ontology on and off…
        </div>
      )}

      {result && (
        <div className="mt-8 animate-rise space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-navy-900">
              Verdict
            </h2>
            {result.model && (
              <span className="font-mono text-[11px] text-subtle">
                model: {result.model}
              </span>
            )}
          </div>
          <ScoreCard sc={result.scorecard} />
          <div className="grid gap-4 md:grid-cols-2">
            <VariantCard v={result.on} />
            <VariantCard v={result.off} />
          </div>
        </div>
      )}
    </div>
  );
}
