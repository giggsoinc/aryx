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
 * Text-alternative summary for screen readers: a full `aria-label` on the
 * chart container (not just Plotly's own hover tooltips) — `spec.summary`
 * carries that, built alongside the trace data itself in plotlySpecs.ts.
 * No visible per-item rows underneath the chart; the data lives in the
 * chart itself.
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
    </div>
  );
}
