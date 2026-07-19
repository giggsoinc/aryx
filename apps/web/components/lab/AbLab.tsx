"use client";

import { useEffect, useState } from "react";
import { Database, FlaskConical, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import type { AbResult } from "@/lib/types";
import { ReasonerCard } from "./ReasonerCard";
import { ScoreCard } from "./ScoreCard";
import { VariantCard } from "./VariantCard";

/** The Accuracy Lab: same model, same question, ontology on vs off. */
export function AbLab() {
  const { workspaceId } = useWorkspace();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AbResult | null>(null);

  // Workspace data state: null = loading, 0 = empty, >0 = populated.
  const [entityCount, setEntityCount] = useState<number | null>(null);
  const [examples, setExamples] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    setEntityCount(null); setExamples([]); setResult(null); setError(null);
    (async () => {
      const summary = await api.dataSummary(workspaceId).catch(() => null);
      const total = summary && !("error" in summary) ? summary.total_entities : 0;
      if (!live) return;
      setEntityCount(total);
      // Build example questions from REAL entities so a click actually grounds.
      const topType = summary?.types?.[0]?.name;
      if (total > 0 && topType) {
        const page = await api.dataEntities(workspaceId, topType, 3, 0)
          .catch(() => null);
        if (!live) return;
        const names = (page && "items" in page ? page.items || [] : [])
          .map((e) => e.name).filter(Boolean);
        setExamples(names.slice(0, 3).map((n) => `Tell me about ${n}`));
      }
    })();
    return () => { live = false; };
  }, [workspaceId]);

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

  const isEmpty = entityCount === 0;

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

      {isEmpty ? (
        <EmptyState />
      ) : (
        <>
          <div className="mt-6 flex items-center gap-2 rounded-2xl border border-navy-100 bg-white p-2 shadow-soft">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run(q)}
              placeholder="Ask a question about this workspace's entities…"
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

          {examples.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-subtle">Try a real entity:</span>
              {examples.map((ex) => (
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
          )}

          <div className="mt-4">
            <ReasonerCard />
          </div>
        </>
      )}

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
            <h2 className="text-sm font-semibold text-navy-900">Verdict</h2>
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

/** Shown when the active workspace has no entities — the Lab needs data to
 *  contrast grounded vs ungrounded, so guide the user instead of returning a
 *  confusing all-zeros verdict. */
function EmptyState() {
  return (
    <div className="mt-6 rounded-2xl border border-navy-100 bg-white p-8 text-center shadow-soft">
      <Database size={26} className="mx-auto text-navy-300" />
      <h2 className="mt-3 font-serif text-xl text-navy-900">
        This workspace has no data yet.
      </h2>
      <p className="mx-auto mt-2 max-w-md text-[13.5px] leading-relaxed text-subtle">
        The Lab contrasts a grounded answer against an ungrounded one — it needs
        a workspace with resolved entities. Switch to one that has data using the
        picker at the top right, or onboard a source.
      </p>
      <Link href="/start"
        className="focus-ring mt-5 inline-flex items-center gap-1.5 rounded-xl bg-navy-800 px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-navy-700">
        <Sparkles size={14} /> Onboard data
      </Link>
    </div>
  );
}
