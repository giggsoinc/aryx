"use client";

import dynamic from "next/dynamic";
import type { ChartSpec } from "@/lib/plotlySpecs";

// plotly.js-dist-min touches `self`/`window` at module load time, which
// doesn't exist during Next.js's server-side prerender pass — dynamic
// import with ssr:false keeps it out of any server bundle entirely, loaded
// only once this component actually mounts in the browser.
const Plot = dynamic(
  () => import("react-plotly.js/factory").then(async (factory) => {
    const Plotly = (await import("plotly.js-dist-min")).default;
    return factory.default(Plotly);
  }),
  { ssr: false },
);

/** Generic renderer for every Plotly-backed chart type (C15).
 *
 * One component instead of one per chart type — `plotlySpecs.ts` is where
 * "which Plotly trace(s) for this chart_type" actually lives; this
 * component only draws whatever `data`/`layout` it's given.
 *
 * Same accessibility contract every chart component in this app already
 * follows (BarChart/BoxPlotChart/GroupedBarChart before this): a full
 * `aria-label` text-alternative summary (not just Plotly's own hover
 * tooltips) plus a visible, keyboard-focusable per-item text row
 * underneath the chart — `spec.summary`/`spec.rows` carry that, built
 * alongside the trace data itself in plotlySpecs.ts so the two can never
 * drift apart.
 */
// dataviz skill (interaction.md): tooltips enhance but hit targets need
// room to breathe, and every value must stay readable in the primary ink,
// not the series color — hence a fixed hoverlabel style instead of Plotly's
// per-trace-colored default box.
const BASE_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { family: "system-ui, -apple-system, sans-serif", size: 11, color: "#475569" },
  margin: { t: 8, r: 8, b: 32, l: 40 },
  showlegend: false,
  hoverdistance: 30,
  hoverlabel: { bgcolor: "#0f172a", bordercolor: "#0f172a", font: { color: "#f8fafc", size: 11 } },
};

// Zoom/pan/reset only appear on hover (displayModeBar: "hover") so they
// don't clutter a dashboard grid of small cards at rest; lasso/select/
// autoscale/3d buttons are irrelevant to these 2D chart types.
const BASE_CONFIG: Partial<Plotly.Config> = {
  displayModeBar: "hover",
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
  responsive: true,
};

interface Props {
  spec: ChartSpec;
  height?: number;
}

export function PlotlyChart({ spec, height = 280 }: Props) {
  return (
    <div role="img" aria-label={spec.summary}>
      <div className="focus-ring w-full" tabIndex={0} style={{ height }}>
        <Plot
          data={spec.data}
          layout={{ ...BASE_LAYOUT, ...spec.layout }}
          config={{ ...BASE_CONFIG, ...spec.config }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>
      {spec.rows.length > 0 && (
        <div className="mt-1 space-y-1">
          {spec.rows.map((r) => (
            <div key={r.key} tabIndex={0} title={r.text}
                className="focus-ring flex items-center justify-between rounded px-1 py-0.5 text-xs text-navy-600 outline-none focus:bg-navy-50">
              <span className="font-medium text-navy-700">{r.label}</span>
              <span>{r.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
