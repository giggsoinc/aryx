"use client";

import { AlertTriangle, Eye, Lock } from "lucide-react";
import type { Brief } from "@/lib/types";

interface Props {
  /** What Aryx read from the uploaded data. Never human-editable. */
  understood: Brief;
  /** Optional: divergences from the customer brief. */
  divergences?: string[];
  /** Optional: customer objectives / questions this data cannot answer. */
  gaps?: string[];
  /** Shown when the data reading was produced by offline heuristics. */
  fallback?: boolean;
  /** True when this reading was promoted into the brief (customer skipped it). */
  promoted?: boolean;
  className?: string;
}

const FIELDS: Array<[keyof Brief, string]> = [
  ["domain", "Domain"],
  ["aim", "Aim"],
  ["scope", "Scope"],
];

const LIST_FIELDS: Array<[keyof Brief, string]> = [
  ["objectives", "Objectives"],
  ["roles", "Roles"],
  ["questions", "Proof questions"],
];

/**
 * Read-only view of what Aryx understood from the ingested data.
 *
 * This is informational, not an input. The customer brief — captured before
 * upload — is the editable, authoritative one; this panel is the machine's
 * reading of the data reported back. Making it editable would create two
 * competing sources of truth, which is exactly the ambiguity the brief-first
 * ordering exists to remove.
 */
export function UnderstandingPanel({
  understood, divergences = [], gaps = [], fallback = false,
  promoted = false, className = "",
}: Props) {
  const list = (v: unknown) => (Array.isArray(v) ? (v as string[]) : []);
  const has = (v: unknown) =>
    Array.isArray(v) ? v.length > 0 : String(v || "").trim() !== "";
  const empty = ![...FIELDS, ...LIST_FIELDS].some(([k]) => has(understood[k]));

  return (
    <section
      className={`rounded-xl border border-navy-100 bg-navy-50/40 p-4 ${className}`}
    >
      <div className="flex items-center gap-2">
        <Eye size={14} className="text-steel-600" />
        <div className="text-[10px] font-bold uppercase tracking-wide text-navy-500">
          What we understood from your data
        </div>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-navy-100 px-2 py-0.5 text-[10px] font-semibold text-navy-600">
          <Lock size={9} /> Read-only
        </span>
      </div>
      <p className="mt-1.5 text-[11px] text-subtle">
        Aryx&apos;s reading of the uploaded data. Informational — it does not
        replace your brief. To change what Aryx targets, edit the brief.
      </p>

      {empty ? (
        <p className="mt-3 text-[12px] text-subtle">
          Nothing read yet — upload data to generate this.
        </p>
      ) : (
        <dl className="mt-3 space-y-2.5">
          {FIELDS.filter(([k]) => has(understood[k])).map(([k, label]) => (
            <div key={String(k)}>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-navy-500">
                {label}
              </dt>
              <dd className="mt-0.5 whitespace-pre-wrap text-[13px] text-navy-800">
                {String(understood[k])}
              </dd>
            </div>
          ))}
          {LIST_FIELDS.filter(([k]) => has(understood[k])).map(([k, label]) => (
            <div key={String(k)}>
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-navy-500">
                {label}
              </dt>
              <dd className="mt-0.5">
                <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-navy-800">
                  {list(understood[k]).map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {divergences.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800">
            <AlertTriangle size={12} /> Where the data disagrees with your brief
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[12px] text-amber-900">
            {divergences.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </div>
      )}

      {gaps.length > 0 && (
        <div className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2">
          <div className="text-[11px] font-semibold text-rose-800">
            Your brief asks for things this data cannot answer
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[12px] text-rose-900">
            {gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}

      {promoted && (
        <p className="mt-2 text-[11px] text-amber-700">
          No brief was captured before upload, so this reading was used as your
          brief. Writing a real one on the Brief tab replaces it.
        </p>
      )}
      {fallback && (
        <p className="mt-2 text-[11px] text-subtle">
          Produced by offline heuristics — set an answer model in Settings for a
          richer reading.
        </p>
      )}
    </section>
  );
}
