"use client";

import type { DataSummary } from "@/lib/types";
import { typeColor } from "@/lib/typeColor";

/** Top strip: what's in the workspace + where it came from + the dedup story. */
export function SummaryStrip({ summary }: { summary: DataSummary }) {
  return (
    <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
      <div className="rounded-2xl border border-navy-100 bg-white p-4 shadow-soft">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.13em] text-subtle">
          {summary.total_entities} entities · {summary.type_count} types
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {summary.types.map((t, i) => (
            <div key={t.name}
                 className="flex-1 rounded-xl px-3 py-2.5 text-white"
                 style={{ background: typeColor(i), minWidth: 92 }}>
              <div className="font-display text-2xl leading-none">{t.count}</div>
              <div className="mt-1 text-[11px] font-medium opacity-95">{t.name}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-navy-100 bg-white p-4 shadow-soft">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.13em] text-subtle">
          From {summary.sources.length} source{summary.sources.length === 1 ? "" : "s"}
        </h3>
        <div className="mt-3 space-y-2">
          {summary.sources.map((s) => {
            const max = summary.sources[0]?.count || 1;
            return (
              <div key={s.source} className="flex items-center gap-3 text-[12.5px]">
                <span className="w-32 flex-none truncate font-mono text-[11px] font-medium text-navy-800">
                  {s.source}
                </span>
                <span className="h-1.5 rounded bg-steel-500"
                      style={{ width: `${Math.round((s.count / max) * 60) + 12}%` }} />
                <span className="ml-auto text-[11px] text-subtle">{s.count} records</span>
              </div>
            );
          })}
          {summary.sources.length === 0 && (
            <p className="text-[12px] text-subtle">No provenance recorded.</p>
          )}
        </div>
        {summary.duplicates_merged > 0 && (
          <p className="mt-3 text-[11px] text-subtle">
            {summary.source_records} source records → {summary.total_entities}{" "}
            entities (<b className="text-navy-700">{summary.duplicates_merged} duplicates merged</b>).
          </p>
        )}
      </div>
    </div>
  );
}
