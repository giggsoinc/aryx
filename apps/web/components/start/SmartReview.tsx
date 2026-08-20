"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, FileText, Loader2, Sparkles } from "lucide-react";
import { UnderstandingPanel } from "@/components/understanding/UnderstandingPanel";
import { api } from "@/lib/api";
import type { Brief, SmartUnderstandResult } from "@/lib/types";
import { StepShell } from "./StepShell";

interface Props {
  workspaceId: number;
  files: File[];
  result: SmartUnderstandResult;
  onBuilt: (jobId: string | null) => void;
  onBack: () => void;
  onAddMore: () => void;
}

/**
 * After data is chosen: show what Aryx understood FROM THE DATA, plus the
 * graph plan, and confirm the build.
 *
 * The understanding panel is deliberately READ-ONLY. The editable brief is
 * the customer's, captured before upload on the Brief step — this panel is
 * Aryx reporting back what it read, and letting a human retype it here would
 * blur the two. Divergences and gaps are surfaced instead: if the reading is
 * wrong, the fix is to correct the brief, not to edit the reading.
 */
export function SmartReview({
  workspaceId, files, result, onBuilt, onBack, onAddMore,
}: Props) {
  const understood: Brief = result.brief || {};
  const customerBrief: Brief = result.customer_brief || {};
  // The server decides this, not us. Re-deriving it here drifted from
  // aryx.brief.is_populated — a brief carrying only `source_docs` read as
  // populated in the UI while the server promoted the derived one over it.
  const hasCustomerBrief = result.customer_brief_populated ?? false;
  const [hint, setHint] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const plan = result.graph_plan || {};
  const primaries = plan.primary_types || [];
  const dims = plan.dimension_types || [];
  const rels = plan.relationships || [];

  const build = async () => {
    setBusy(true);
    setError(null);
    try {
      // Fold follow-up answers into aim/scope lightly
      const extra = [
        ...Object.entries(answers)
          .filter(([, v]) => v.trim())
          .map(([k, v]) => `${k}: ${v}`),
        ...(hint.trim() ? [`hint: ${hint.trim()}`] : []),
      ].join("; ");
      // Posted as the DERIVED reading — the server stores it in
      // data_understanding and leaves the customer brief untouched.
      const derived: Brief = {
        ...understood,
        aim: extra
          ? `${understood.aim || ""}\nUser notes: ${extra}`.trim()
          : understood.aim,
      };
      await api.smartApply(
        workspaceId, derived, plan as Record<string, unknown>, result.plan_id,
      );
      const primary = primaries[0];
      const otype = primary?.name || "Document";
      const keys = (primary?.match_keys || ["name"]).join(",");
      const r = await api.uploadFiles(
        workspaceId, files, otype, keys, plan as Record<string, unknown>,
      );
      onBuilt(r.job_id || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Build failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <StepShell progress={55}>
      <div className="flex items-center gap-2 text-steel-600">
        <Sparkles size={18} />
        <span className="text-[11px] font-bold uppercase tracking-[0.12em]">
          Smart review · read through your brief
        </span>
      </div>
      <h1 className="mt-2 max-w-2xl text-center font-display text-[1.85rem] leading-tight text-navy-900">
Here&apos;s what Aryx read in this data
      </h1>
      <p className="mt-2 max-w-xl text-center text-[13px] text-subtle">
        Read from samples of your files against your brief, using your Settings
        model (Gemini, Ollama, or any provider). Review, then build the graph.
        {result.fallback && (
          <span className="mt-1 block text-amber-700">
            Used offline heuristics — set an answer model in Settings for a richer plan.
          </span>
        )}
      </p>

      <div className="mt-6 w-full max-w-2xl space-y-4">
        <section className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
          <div className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
            What we see
          </div>
          <p className="mt-2 text-[13px] text-navy-800">{result.summary}</p>
        </section>

        <section className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
          <div className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
            Graph plan
          </div>
          <ul className="mt-2 space-y-1 text-[13px] text-navy-800">
            {primaries.map((p, i) => (
              <li key={`p-${i}`}>
                <b>Row type:</b> {p.name}
                {p.match_keys?.length ? (
                  <span className="text-subtle"> · keys {p.match_keys.join(", ")}</span>
                ) : null}
              </li>
            ))}
            {dims.map((d, i) => (
              <li key={`d-${i}`}>
                <b>Dimension:</b> {d.name}
                {d.source_column ? (
                  <span className="text-subtle"> ← column {d.source_column}</span>
                ) : null}
              </li>
            ))}
            {rels.map((r, i) => (
              <li key={`r-${i}`} className="text-subtle">
                {r.from} —[{r.name}]→ {r.to}
                {r.via_column ? ` (via ${r.via_column})` : ""}
              </li>
            ))}
            {!primaries.length && !dims.length && (
              <li className="text-subtle">No types proposed yet.</li>
            )}
          </ul>
          {(plan.outcomes || []).length > 0 && (
            <p className="mt-2 text-[12px] text-subtle">
              Outcomes: {(plan.outcomes || []).join(" · ")}
            </p>
          )}
        </section>

        {hasCustomerBrief && (
          <section className="rounded-xl border border-steel-400/50 bg-white p-4 shadow-soft">
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-steel-600" />
              <div className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
                Your brief — this is what we planned against
              </div>
            </div>
            {customerBrief.aim && (
              <p className="mt-2 text-[13px] text-navy-800">{customerBrief.aim}</p>
            )}
            {(customerBrief.questions || []).length > 0 && (
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[12px] text-navy-800">
                {(customerBrief.questions || []).map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            )}
            <Link
              href="/brief"
              className="focus-ring mt-2 inline-block text-[12px] font-semibold text-steel-600 underline"
            >
              Edit brief →
            </Link>
          </section>
        )}

        <UnderstandingPanel
          understood={understood}
          divergences={result.divergences || []}
          gaps={result.gaps || []}
          fallback={result.fallback}
          promoted={!hasCustomerBrief}
        />

        {(result.follow_ups || []).length > 0 && (
          <section className="rounded-xl border border-navy-100 bg-white p-4 shadow-soft space-y-2">
            <div className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
              Optional — quick answers (don&apos;t overthink)
            </div>
            {(result.follow_ups || []).map((q, i) => {
              const id = q.id || `q${i}`;
              return (
                <label key={id} className="block text-[12px] text-navy-800">
                  {q.question}
                  {q.why && (
                    <span className="block text-[11px] text-subtle">{q.why}</span>
                  )}
                  <input
                    className="focus-ring mt-1 w-full rounded-lg border border-navy-100 px-2.5 py-1.5 text-[13px]"
                    value={answers[id] || ""}
                    onChange={(e) =>
                      setAnswers((a) => ({ ...a, [id]: e.target.value }))
                    }
                    placeholder="Optional"
                  />
                </label>
              );
            })}
          </section>
        )}

        {(result.suggested_documents || []).length > 0 && (
          <section className="rounded-xl border border-dashed border-steel-400/50 bg-white/80 p-4">
            <div className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
              Sharper outcome — add these if you have them
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] text-navy-800">
              {(result.suggested_documents || []).map((d, i) => (
                <li key={i}>
                  <b>{d.what}</b>
                  {d.why ? <span className="text-subtle"> — {d.why}</span> : null}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={onAddMore}
              className="focus-ring mt-3 text-[12px] font-semibold text-steel-600 underline"
            >
              Add more files →
            </button>
          </section>
        )}

        <label className="block text-[11px] text-subtle">
          Optional extra hint for this build
          <input
            className="focus-ring mt-1 w-full rounded-lg border border-navy-100 px-2.5 py-1.5 text-[13px] text-navy-800"
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="e.g. I care about cities I travelled and merchant spend"
          />
        </label>
      </div>

      {error && (
        <div className="mt-3 w-full max-w-2xl rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {error}
        </div>
      )}

      <div className="mt-7 flex w-full max-w-2xl items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="focus-ring text-[12px] text-subtle hover:text-navy-700"
        >
          ← Back
        </button>
        <button
          type="button"
          disabled={busy || files.length === 0}
          onClick={build}
          className="focus-ring inline-flex items-center gap-2 rounded-2xl bg-navy-800 px-6 py-3 text-[14px] font-semibold text-white hover:bg-navy-700 disabled:opacity-40"
        >
          {busy ? (
            <><Loader2 size={16} className="animate-spin" /> Building…</>
          ) : (
            <>Looks right — build graph <ArrowRight size={16} /></>
          )}
        </button>
      </div>
      {hint.trim() && (
        <p className="mt-2 max-w-2xl text-center text-[11px] text-subtle">
          Tip: go Back → re-upload with your hint in Smart review after we add
          re-run understand, or put the goal in Aim above.
        </p>
      )}
    </StepShell>
  );
}
