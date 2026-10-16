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
  // Set by ChartFullscreenModal only. In the small dashboard-grid card,
  // Plotly's own "shrink to fit" behavior stands — some tick labels go
  // unlabeled at that size, same as before. Fullscreen has room to do
  // better: a plain vertical bar chart with many categories is flipped to
  // horizontal bars, one per row, with the chart made tall enough to hold
  // them all — so scrolling DOWN the modal reveals every label at full
  // legibility instead of squeezing or side-scrolling.
  fullscreen?: boolean;
}

const MIN_CATEGORIES_FOR_TALL_LAYOUT = 16;
const PX_PER_CATEGORY = 28;

function maxCategoryCount(data: ChartSpec["data"]): number {
  let max = 0;
  for (const trace of data) {
    const x = (trace as { x?: unknown[] }).x;
    if (Array.isArray(x) && x.length > max) max = x.length;
  }
  return max;
}

// Only a plain, single-orientation bar trace is safe to flip — a swap of x
// and y is purely a display transform (still the same values, same
// governed numbers), but it only makes sense for this one trace shape.
function isPlainVerticalBar(data: ChartSpec["data"]): boolean {
  return data.length > 0 && data.every((trace) => {
    const t = trace as { type?: string; orientation?: string };
    return t.type === "bar" && t.orientation !== "h";
  });
}

function toHorizontalBars(data: ChartSpec["data"]): ChartSpec["data"] {
  return data.map((trace) => {
    const t = trace as Record<string, unknown>;
    return { ...t, x: t.y, y: t.x, orientation: "h" } as ChartSpec["data"][number];
  });
}

export function PlotlyChart({ spec, height = 280, fullscreen = false }: Props) {
  const categoryCount = maxCategoryCount(spec.data);
  const useTallHorizontalBars = fullscreen
    && categoryCount > MIN_CATEGORIES_FOR_TALL_LAYOUT
    && isPlainVerticalBar(spec.data);

  const data = useTallHorizontalBars ? toHorizontalBars(spec.data) : spec.data;
  const plotHeight = useTallHorizontalBars ? categoryCount * PX_PER_CATEGORY : height;
  const layout: Partial<Plotly.Layout> = useTallHorizontalBars
    ? {
        ...BASE_LAYOUT,
        ...spec.layout,
        // The categorical axis moved from x to y in the flip — give it room
        // for full label text instead of whatever xaxis tickfont/gridcolor
        // the original vertical-bar spec set.
        xaxis: { gridcolor: "#e5e9f2" },
        yaxis: { automargin: true, tickfont: { size: 10 } },
      }
    : { ...BASE_LAYOUT, ...spec.layout };

  return (
    <div role="img" aria-label={spec.summary}>
      <div className="focus-ring w-full" tabIndex={0} style={{ height: plotHeight }}>
        <Plot
          data={data}
          layout={layout}
          config={{ ...BASE_CONFIG, ...spec.config }}
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>
    </div>
  );
}
