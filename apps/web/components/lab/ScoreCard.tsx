"use client";

import { Check, X } from "lucide-react";
import type { AbScorecard } from "@/lib/types";

/** The side-by-side verdict strip — grounded vs asserted, at a glance. */
export function ScoreCard({ sc }: { sc: AbScorecard }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-navy-100 bg-navy-100 sm:grid-cols-4">
      <BoolMetric label="Grounded" on={sc.grounded.on} off={sc.grounded.off} />
      <NumMetric label="Citations" on={sc.citations.on} off={sc.citations.off} />
      <NumMetric label="Source records" on={sc.source_records.on}
                 off={sc.source_records.off} />
      <NumMetric label="Evidence used" on={sc.evidence_used.on}
                 off={sc.evidence_used.off} />
    </div>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-white px-4 py-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-subtle">
        {label}
      </div>
      <div className="mt-1.5 flex items-center gap-3">{children}</div>
    </div>
  );
}

function BoolMetric({ label, on, off }: { label: string; on: boolean; off: boolean }) {
  return (
    <Cell label={label}>
      <Pill ok={on} text="On" />
      <Pill ok={off} text="Off" />
    </Cell>
  );
}

function NumMetric({ label, on, off }: { label: string; on: number; off: number }) {
  return (
    <Cell label={label}>
      <span className="text-sm font-semibold text-emerald-600">{on}</span>
      <span className="text-[11px] text-subtle">on</span>
      <span className="text-sm font-semibold text-navy-400">{off}</span>
      <span className="text-[11px] text-subtle">off</span>
    </Cell>
  );
}

function Pill({ ok, text }: { ok: boolean; text: string }) {
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold " +
        (ok ? "bg-emerald-50 text-emerald-700" : "bg-navy-50 text-navy-400")
      }
    >
      {ok ? <Check size={11} /> : <X size={11} />}
      {text}
    </span>
  );
}
