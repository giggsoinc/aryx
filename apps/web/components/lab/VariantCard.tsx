"use client";

import { ShieldCheck, ShieldOff } from "lucide-react";
import type { AbVariant } from "@/lib/types";

/** One side of the comparison: the answer + its verified grounding. */
export function VariantCard({ v }: { v: AbVariant }) {
  const on = v.grounded_in_ontology;
  const g = v.grounding;
  const pct = Math.round((g.score || 0) * 100);
  return (
    <div
      className={
        "flex flex-col rounded-2xl border bg-white p-5 shadow-soft " +
        (on ? "border-steel-400/50" : "border-navy-100")
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {on ? <ShieldCheck size={16} className="text-steel-600" />
              : <ShieldOff size={16} className="text-navy-400" />}
          <span className="text-sm font-semibold text-navy-900">{v.label}</span>
        </div>
        <span
          className={
            "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide " +
            (g.grounded ? "bg-emerald-50 text-emerald-700"
                        : "bg-rose-50 text-rose-700")
          }
        >
          {g.grounded ? "Grounded" : "Ungrounded"}
        </span>
      </div>

      <p className="mt-3 whitespace-pre-wrap text-[13.5px] leading-relaxed text-navy-800">
        {v.answer || "(no answer)"}
      </p>

      {on && (
        <div className="mt-4 border-t border-navy-100 pt-3">
          <div className="flex items-center justify-between text-[11px] text-subtle">
            <span>Evidence used</span>
            <span className="font-medium text-navy-700">
              {g.cited_count}/{g.entity_count} entities · {pct}%
            </span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-navy-100">
            <div className="h-full rounded-full bg-steel-500"
                 style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {g.citations.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-subtle">
            Citations
          </div>
          <ul className="mt-2 space-y-1.5">
            {g.citations.map((c) => (
              <li key={`${c.marker}-${c.entity_id}-${c.record_id}`}
                  className="flex items-start gap-2 text-[12px]">
                <span className="mt-0.5 inline-flex size-4 flex-none items-center justify-center rounded bg-navy-800 text-[9px] font-bold text-white">
                  {c.marker}
                </span>
                <span className="text-navy-700">
                  <span className="font-medium text-navy-900">{c.entity_name}</span>
                  <span className="text-subtle"> [{c.entity_type}]</span>
                  {" — "}
                  <span className="font-mono text-[11px] text-steel-600">
                    {c.system}.{c.dataset}#{c.record_id}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!on && (
        <p className="mt-4 border-t border-navy-100 pt-3 text-[11px] italic text-subtle">
          No workspace grounding — the same model answering from its own
          parameters. Nothing here is traceable to a source record.
        </p>
      )}
    </div>
  );
}
