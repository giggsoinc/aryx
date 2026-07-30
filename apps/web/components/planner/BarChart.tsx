"use client";

/** A small, dependency-free, accessible horizontal bar chart.
 *
 * No charting library is installed in this app, and this component's needs
 * are simple (a handful of categories per chart) — hand-rolling keeps the
 * bundle small and gives full control over accessibility, which C15
 * explicitly requires (keyboard navigation, contrast, text alternatives):
 * every bar is a focusable element with a visible label+value (not just a
 * hover tooltip), and the chart carries a full textual summary via
 * `aria-label` as the actual text alternative — not decoration.
 */
export interface BarDatum {
  label: string;
  value: number;
  displayValue: string;
  warning?: string;
}

interface Props {
  title: string;
  data: BarDatum[];
}

export function BarChart({ title, data }: Props) {
  const max = Math.max(...data.map((d) => Math.abs(d.value)), 1e-9);
  const summary = `Bar chart: ${title}. ` +
    data.map((d) => `${d.label} ${d.displayValue}${d.warning ? ` (${d.warning})` : ""}`).join(", ") + ".";

  return (
    <div role="img" aria-label={summary} className="space-y-1.5">
      {data.map((d) => {
        const pct = Math.max(2, Math.round((Math.abs(d.value) / max) * 100));
        return (
          <div key={d.label}
               tabIndex={0}
               title={`${d.label}: ${d.displayValue}${d.warning ? ` — ${d.warning}` : ""}`}
               className="focus-ring group flex items-center gap-2 rounded px-1 py-0.5 outline-none focus:bg-navy-50">
            <span className="w-20 shrink-0 truncate text-xs font-medium text-navy-700">{d.label}</span>
            <span className="h-4 flex-1 overflow-hidden rounded bg-navy-50">
              <span
                className={`block h-full rounded transition-all ${d.warning ? "bg-amber-400" : "bg-sky-500"} group-focus:bg-navy-700`}
                style={{ width: `${pct}%` }}
              />
            </span>
            <span className="w-16 shrink-0 text-right text-xs text-navy-600">{d.displayValue}</span>
          </div>
        );
      })}
    </div>
  );
}
