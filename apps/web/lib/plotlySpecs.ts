// Plotly trace builders for the Frontend Dashboard Renderer (C15).
//
// One pure `build<Type>Spec` function per chart type — each takes only
// already-computed AnalysisResultRow/KpiResult values (never raw data, never
// recomputing a governed value) and returns a ChartSpec: the Plotly
// data/layout plus the same accessibility contract every chart component in
// this app already carries (a full aria-label summary + a focusable
// per-item text fallback row — see PlotlyChart.tsx).
//
// Palette: computed and validated with the dataviz skill's
// scripts/validate_palette.js (categorical ΔE / contrast checks), not
// eyeballed — rooted in this app's existing sky/amber/navy accents rather
// than a generic default. Categorical hues are used in FIXED order, never
// cycled or reassigned when a filter changes the series count.
import type { Data, Layout, Config } from "plotly.js";
import type { AnalysisResultRow } from "./types";

export interface ChartRow {
  key: string;
  label: string;
  text: string;
}

export interface ChartSpec {
  data: Data[];
  layout: Partial<Layout>;
  config?: Partial<Config>;
  summary: string;
  rows: ChartRow[];
}

export type Fmt = (value: number | null) => string;

// ── validated palette ──────────────────────────────────────────────────
// Categorical order validated with `validate_palette.js` (CVD ΔE >= 8,
// normal-vision floor >= 15 on every adjacent pair; amber sits last since
// it's this app's reserved warning color — kept usable as an 8th slot, but
// never adjacent to the primary sky slot).
export const CATEGORICAL_PALETTE = [
  "#0284c7", "#059669", "#7c3aed", "#e11d48", "#0891b2", "#65a30d", "#db2777", "#f59e0b",
];
// The fixed primary/compare pair every 2-series chart in this app already
// uses (GroupedBarChart's original convention) — sky vs amber.
export const SERIES_PRIMARY = "#0284c7";
export const SERIES_COMPARE = "#f59e0b";
// One hue (blue), light -> dark, for continuous magnitude (heatmap_matrix,
// calendar_heatmap) — the dataviz skill's validated sequential blue ramp.
export const SEQUENTIAL_COLORSCALE: [number, string][] = [
  [0, "#cde2fb"], [0.15, "#9ec5f4"], [0.3, "#6da7ec"], [0.45, "#3987e5"],
  [0.6, "#2a78d6"], [0.75, "#1c5cab"], [0.9, "#104281"], [1, "#0d366b"],
];

function categoricalColor(i: number): string {
  return CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length];
}

function labelOf(r: AnalysisResultRow): string {
  return r.group_value;
}

// ── bar / line / area / step / donut ────────────────────────────────────

export function buildBarSpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const labels = rows.map(labelOf);
  const values = rows.map((r) => r.value ?? 0);
  const data: Data[] = [{
    type: "bar", x: labels, y: values, marker: { color: SERIES_PRIMARY },
  }];
  return {
    data, layout: { xaxis: { tickfont: { size: 10 } }, yaxis: { gridcolor: "#e5e9f2" } },
    summary: `Bar chart: ${title}. ` + rows.map((r) => `${labelOf(r)} ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({ key: labelOf(r), label: labelOf(r), text: fmt(r.value) })),
  };
}

export function buildDonutSpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const labels = rows.map(labelOf);
  const values = rows.map((r) => r.value ?? 0);
  const data: Data[] = [{
    type: "pie", labels, values, hole: 0.5, textinfo: "label+percent",
    marker: { colors: rows.map((_, i) => categoricalColor(i)) },
  }];
  return {
    data, layout: { showlegend: rows.length > 1 },
    summary: `Donut chart: ${title}. ` + rows.map((r) => `${labelOf(r)} ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({ key: labelOf(r), label: labelOf(r), text: fmt(r.value) })),
  };
}

function buildLineLikeSpec(
  rows: AnalysisResultRow[], fmt: Fmt, title: string,
  variant: "line" | "area" | "step",
): ChartSpec {
  const labels = rows.map(labelOf);
  const values = rows.map((r) => r.value ?? 0);
  const data: Data[] = [{
    type: "scatter", mode: "lines+markers", x: labels, y: values,
    line: { color: SERIES_PRIMARY, shape: variant === "step" ? "hv" : "linear", width: 2 },
    marker: { color: SERIES_PRIMARY, size: 6 },
    fill: variant === "area" ? "tozeroy" : "none",
    fillcolor: variant === "area" ? "rgba(2,132,199,0.15)" : undefined,
  }];
  const kind = variant === "area" ? "Area chart" : variant === "step" ? "Step chart" : "Line chart";
  return {
    data,
    // dataviz skill: "the crosshair finds the X" — a vertical spike line
    // tracks the pointer and snaps to the nearest point; "x unified" merges
    // every series into one tooltip at that X instead of one-at-a-time.
    layout: {
      hovermode: "x unified",
      xaxis: {
        tickfont: { size: 10 }, showspikes: true, spikemode: "across",
        spikedash: "dot", spikecolor: "#94a3b8", spikethickness: 1,
      },
      yaxis: { gridcolor: "#e5e9f2" },
    },
    summary: `${kind}: ${title}. ` + rows.map((r) => `${labelOf(r)} ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({ key: labelOf(r), label: labelOf(r), text: fmt(r.value) })),
  };
}

export const buildLineSpec = (rows: AnalysisResultRow[], fmt: Fmt, title: string) =>
  buildLineLikeSpec(rows, fmt, title, "line");
export const buildAreaSpec = (rows: AnalysisResultRow[], fmt: Fmt, title: string) =>
  buildLineLikeSpec(rows, fmt, title, "area");
export const buildStepSpec = (rows: AnalysisResultRow[], fmt: Fmt, title: string) =>
  buildLineLikeSpec(rows, fmt, title, "step");

// ── scatter / bubble (row_points) ───────────────────────────────────────

export function buildScatterSpec(rows: AnalysisResultRow[], title: string): ChartSpec {
  const data: Data[] = [{
    type: "scatter", mode: "markers", x: rows.map((r) => r.x), y: rows.map((r) => r.y),
    text: rows.map(labelOf), marker: { color: SERIES_PRIMARY, size: 8 },
  }];
  return {
    data, layout: { xaxis: { gridcolor: "#e5e9f2" }, yaxis: { gridcolor: "#e5e9f2" } },
    summary: `Scatter chart: ${title}. ` +
      rows.map((r) => `${labelOf(r)}: x ${r.x}, y ${r.y}`).join(", ") + ".",
    rows: rows.map((r) => ({ key: labelOf(r), label: labelOf(r), text: `x ${r.x}, y ${r.y}` })),
  };
}

export function buildBubbleSpec(rows: AnalysisResultRow[], title: string): ChartSpec {
  const sizes = rows.map((r) => r.size ?? 0);
  const maxSize = Math.max(...sizes, 1e-9);
  const data: Data[] = [{
    type: "scatter", mode: "markers", x: rows.map((r) => r.x), y: rows.map((r) => r.y),
    text: rows.map(labelOf),
    marker: {
      color: SERIES_PRIMARY, size: sizes, sizemode: "area",
      sizeref: (2 * maxSize) / (40 ** 2), sizemin: 4, opacity: 0.75,
    },
  }];
  return {
    data, layout: { xaxis: { gridcolor: "#e5e9f2" }, yaxis: { gridcolor: "#e5e9f2" } },
    summary: `Bubble chart: ${title}. ` +
      rows.map((r) => `${labelOf(r)}: x ${r.x}, y ${r.y}, size ${r.size}`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: labelOf(r), label: labelOf(r), text: `x ${r.x}, y ${r.y}, size ${r.size}`,
    })),
  };
}

// ── box plot (grouped quartiles) ────────────────────────────────────────

export function buildBoxPlotSpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const data: Data[] = [{
    type: "box", x: rows.map(labelOf),
    q1: rows.map((r) => r.q1 ?? 0), median: rows.map((r) => r.value ?? 0), q3: rows.map((r) => r.q3 ?? 0),
    lowerfence: rows.map((r) => r.min ?? 0), upperfence: rows.map((r) => r.max ?? 0),
    marker: { color: SERIES_PRIMARY },
  } as Data];
  return {
    data, layout: { yaxis: { gridcolor: "#e5e9f2" } },
    summary: `Box plot: ${title}. ` +
      rows.map((r) => `${labelOf(r)}: median ${fmt(r.value)}, range ${r.min} to ${r.max}`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: labelOf(r), label: labelOf(r),
      text: `median ${fmt(r.value)}, range ${r.min}–${r.max}`,
    })),
  };
}

// ── grouped bar / slopegraph (two analyses, compare_ref) ────────────────

function mergeByGroup(primary: AnalysisResultRow[], compare: AnalysisResultRow[]) {
  const compareByGroup = new Map(compare.map((r) => [r.group_value, r]));
  return primary.map((r) => ({ label: r.group_value, primary: r.value, compare: compareByGroup.get(r.group_value)?.value ?? null }));
}

export function buildGroupedBarSpec(
  primary: AnalysisResultRow[], compare: AnalysisResultRow[],
  primaryLabel: string, compareLabel: string, fmt: Fmt, title: string,
): ChartSpec {
  const merged = mergeByGroup(primary, compare);
  const data: Data[] = [
    { type: "bar", name: primaryLabel, x: merged.map((m) => m.label), y: merged.map((m) => m.primary ?? 0),
     marker: { color: SERIES_PRIMARY } },
    { type: "bar", name: compareLabel, x: merged.map((m) => m.label), y: merged.map((m) => m.compare ?? 0),
     marker: { color: SERIES_COMPARE } },
  ];
  return {
    data,
    layout: { barmode: "group", showlegend: true, hovermode: "x unified", yaxis: { gridcolor: "#e5e9f2" } },
    summary: `Grouped bar chart: ${title}. ` +
      merged.map((m) => `${m.label}: ${primaryLabel} ${fmt(m.primary)}, ${compareLabel} ${fmt(m.compare)}`).join(", ") + ".",
    rows: merged.map((m) => ({
      key: m.label, label: m.label, text: `${primaryLabel} ${fmt(m.primary)} · ${compareLabel} ${fmt(m.compare)}`,
    })),
  };
}

export function buildSlopegraphSpec(
  primary: AnalysisResultRow[], compare: AnalysisResultRow[],
  primaryLabel: string, compareLabel: string, fmt: Fmt, title: string,
): ChartSpec {
  const merged = mergeByGroup(primary, compare);
  const data: Data[] = merged.map((m, i) => ({
    type: "scatter", mode: "lines+markers", name: m.label,
    x: [primaryLabel, compareLabel], y: [m.primary ?? 0, m.compare ?? 0],
    line: { color: categoricalColor(i) }, marker: { color: categoricalColor(i), size: 8 },
  }));
  return {
    data,
    layout: {
      showlegend: merged.length <= 8, hovermode: "x unified",
      yaxis: { gridcolor: "#e5e9f2" },
    },
    summary: `Slopegraph: ${title}. ` +
      merged.map((m) => `${m.label}: ${fmt(m.primary)} -> ${fmt(m.compare)}`).join(", ") + ".",
    rows: merged.map((m) => ({
      key: m.label, label: m.label, text: `${fmt(m.primary)} → ${fmt(m.compare)}`,
    })),
  };
}

// ── histogram ────────────────────────────────────────────────────────────

export function buildHistogramSpec(rows: AnalysisResultRow[], title: string): ChartSpec {
  const grouped = rows.length > 1;
  const data: Data[] = rows.map((r, i) => {
    const buckets = r.buckets ?? [];
    return {
      type: "bar", name: r.group_value === "_all_" ? title : r.group_value,
      x: buckets.map((b) => (b.bucket_start + b.bucket_end) / 2),
      y: buckets.map((b) => b.count),
      marker: { color: categoricalColor(i) }, opacity: grouped ? 0.7 : 1,
    };
  });
  return {
    data,
    layout: {
      barmode: grouped ? "overlay" : "relative", bargap: 0.05, showlegend: grouped,
      hovermode: grouped ? "x unified" : "closest",
      yaxis: { gridcolor: "#e5e9f2" },
    },
    summary: `Histogram: ${title}. ` +
      rows.map((r) => `${r.group_value}: ${(r.buckets ?? []).reduce((n, b) => n + b.count, 0)} observations`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: r.group_value, label: r.group_value === "_all_" ? title : r.group_value,
      text: `${(r.buckets ?? []).reduce((n, b) => n + b.count, 0)} observations across ${(r.buckets ?? []).length} buckets`,
    })),
  };
}

// ── crosstab: heatmap_matrix / calendar_heatmap / sankey / treemap / sunburst ──

export function buildHeatmapMatrixSpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const yCats = Array.from(new Set(rows.map((r) => r.group_value)));
  const xCats = Array.from(new Set(rows.map((r) => r.group_value_secondary ?? "")));
  const cell = new Map(rows.map((r) => [`${r.group_value}␟${r.group_value_secondary}`, r.value ?? 0]));
  const z = yCats.map((y) => xCats.map((x) => cell.get(`${y}␟${x}`) ?? 0));
  const data: Data[] = [{
    type: "heatmap", x: xCats, y: yCats, z, colorscale: SEQUENTIAL_COLORSCALE, hoverongaps: false,
  }];
  return {
    data, layout: { xaxis: { tickfont: { size: 10 } }, yaxis: { tickfont: { size: 10 } } },
    summary: `Heatmap: ${title}. ` +
      rows.map((r) => `${r.group_value} × ${r.group_value_secondary}: ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: `${r.group_value}_${r.group_value_secondary}`, label: `${r.group_value} × ${r.group_value_secondary}`,
      text: fmt(r.value),
    })),
  };
}

export function buildSankeySpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const sources = Array.from(new Set(rows.map((r) => r.group_value)));
  const targets = Array.from(new Set(rows.map((r) => r.group_value_secondary ?? "")));
  const nodeLabels = [...sources, ...targets];
  const sourceIndex = new Map(sources.map((s, i) => [s, i]));
  const targetIndex = new Map(targets.map((t, i) => [t, i + sources.length]));
  const data: Data[] = [{
    type: "sankey",
    node: { label: nodeLabels, color: nodeLabels.map((_, i) => categoricalColor(i)), pad: 12, thickness: 14 },
    link: {
      source: rows.map((r) => sourceIndex.get(r.group_value) ?? 0),
      target: rows.map((r) => targetIndex.get(r.group_value_secondary ?? "") ?? 0),
      value: rows.map((r) => Math.max(0, r.value ?? 0)),
    },
  } as Data];
  return {
    data, layout: {},
    summary: `Sankey diagram: ${title}. ` +
      rows.map((r) => `${r.group_value} → ${r.group_value_secondary}: ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: `${r.group_value}_${r.group_value_secondary}`, label: `${r.group_value} → ${r.group_value_secondary}`,
      text: fmt(r.value),
    })),
  };
}

function buildHierarchySpec(
  rows: AnalysisResultRow[], fmt: Fmt, title: string, type: "treemap" | "sunburst",
): ChartSpec {
  const level1s = Array.from(new Set(rows.map((r) => r.group_value)));
  const parentTotal = new Map<string, number>();
  for (const r of rows) parentTotal.set(r.group_value, (parentTotal.get(r.group_value) ?? 0) + (r.value ?? 0));
  const ids = [...level1s, ...rows.map((r) => `${r.group_value}__${r.group_value_secondary}`)];
  const labels = [...level1s, ...rows.map((r) => r.group_value_secondary ?? "")];
  const parents = [...level1s.map(() => ""), ...rows.map((r) => r.group_value)];
  const values = [...level1s.map((l) => parentTotal.get(l) ?? 0), ...rows.map((r) => r.value ?? 0)];
  const data: Data[] = [{
    type, ids, labels, parents, values, branchvalues: "total",
    marker: { colors: ids.map((_, i) => categoricalColor(i)) },
  } as Data];
  return {
    data, layout: {},
    summary: `${type === "treemap" ? "Treemap" : "Sunburst"}: ${title}. ` +
      rows.map((r) => `${r.group_value} → ${r.group_value_secondary}: ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: `${r.group_value}_${r.group_value_secondary}`, label: `${r.group_value} → ${r.group_value_secondary}`,
      text: fmt(r.value),
    })),
  };
}

export const buildTreemapSpec = (rows: AnalysisResultRow[], fmt: Fmt, title: string) =>
  buildHierarchySpec(rows, fmt, title, "treemap");
export const buildSunburstSpec = (rows: AnalysisResultRow[], fmt: Fmt, title: string) =>
  buildHierarchySpec(rows, fmt, title, "sunburst");
// calendar_heatmap shares the exact same crosstab shape as heatmap_matrix
// (one dimension happens to be a date column) — no separate builder needed.
export const buildCalendarHeatmapSpec = buildHeatmapMatrixSpec;

// ── gantt (date_span) ────────────────────────────────────────────────────

export function buildGanttSpec(rows: AnalysisResultRow[], title: string): ChartSpec {
  const withDates = rows.filter((r) => r.start);
  const starts = withDates.map((r) => new Date(r.start as string).getTime());
  const ends = withDates.map((r) => (r.end ? new Date(r.end as string).getTime() : Date.now()));
  const data: Data[] = [{
    type: "bar", orientation: "h", y: withDates.map(labelOf),
    x: withDates.map((_, i) => ends[i] - starts[i]), base: withDates.map((r) => r.start as string),
    marker: { color: SERIES_PRIMARY },
  } as Data];
  return {
    data,
    layout: { xaxis: { type: "date" }, yaxis: { automargin: true, tickfont: { size: 10 } } },
    summary: `Gantt chart: ${title}. ` +
      withDates.map((r) => `${labelOf(r)}: ${r.start} to ${r.end ?? "ongoing"}`).join(", ") + ".",
    rows: withDates.map((r) => ({
      key: labelOf(r), label: labelOf(r), text: `${r.start} – ${r.end ?? "ongoing"}`,
    })),
  };
}

// ── waterfall ────────────────────────────────────────────────────────────

export function buildWaterfallSpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const data: Data[] = [{
    type: "waterfall", x: rows.map(labelOf), y: rows.map((r) => r.value ?? 0),
    connector: { line: { color: "#cbd5e1" } },
    increasing: { marker: { color: SERIES_PRIMARY } },
    decreasing: { marker: { color: SERIES_COMPARE } },
    totals: { marker: { color: "#334155" } },
  } as Data];
  return {
    data, layout: { yaxis: { gridcolor: "#e5e9f2" } },
    summary: `Waterfall chart: ${title}. ` + rows.map((r) => `${labelOf(r)} ${fmt(r.value)}`).join(", ") + ".",
    rows: rows.map((r) => ({ key: labelOf(r), label: labelOf(r), text: fmt(r.value) })),
  };
}

// ── pareto (bar + cumulative % line) ─────────────────────────────────────
// Deliberate, named exception to "never dual-axis": a Pareto chart IS
// bar-plus-cumulative-percentage-line by definition — rendering it any
// other way stops it from being a Pareto chart at all.
export function buildParetoSpec(rows: AnalysisResultRow[], fmt: Fmt, title: string): ChartSpec {
  const sorted = [...rows].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const total = sorted.reduce((n, r) => n + (r.value ?? 0), 0) || 1;
  let running = 0;
  const cumPct = sorted.map((r) => { running += r.value ?? 0; return (running / total) * 100; });
  const data: Data[] = [
    { type: "bar", x: sorted.map(labelOf), y: sorted.map((r) => r.value ?? 0),
     marker: { color: SERIES_PRIMARY }, yaxis: "y" },
    { type: "scatter", mode: "lines+markers", x: sorted.map(labelOf), y: cumPct,
     marker: { color: SERIES_COMPARE }, line: { color: SERIES_COMPARE }, yaxis: "y2" },
  ];
  return {
    data,
    layout: {
      yaxis: { title: { text: "Value" }, gridcolor: "#e5e9f2" },
      yaxis2: { title: { text: "Cumulative %" }, overlaying: "y", side: "right", range: [0, 100] },
    },
    summary: `Pareto chart: ${title}. ` +
      sorted.map((r, i) => `${labelOf(r)} ${fmt(r.value)} (cumulative ${cumPct[i].toFixed(0)}%)`).join(", ") + ".",
    rows: sorted.map((r, i) => ({
      key: labelOf(r), label: labelOf(r), text: `${fmt(r.value)} · cumulative ${cumPct[i].toFixed(0)}%`,
    })),
  };
}

// ── radar (multi-axis, axis_refs) ────────────────────────────────────────

export interface RadarEntry { axis: string; value: number; displayValue: string }

export function buildRadarSpec(entries: RadarEntry[], title: string): ChartSpec {
  const r = [...entries.map((e) => e.value), entries[0]?.value ?? 0];
  const theta = [...entries.map((e) => e.axis), entries[0]?.axis ?? ""];
  const data: Data[] = [{
    type: "scatterpolar", r, theta, fill: "toself",
    line: { color: SERIES_PRIMARY }, marker: { color: SERIES_PRIMARY },
  } as Data];
  return {
    data, layout: { polar: { radialaxis: { visible: true } } },
    summary: `Radar chart: ${title}. ` + entries.map((e) => `${e.axis} ${e.displayValue}`).join(", ") + ".",
    rows: entries.map((e) => ({ key: e.axis, label: e.axis, text: e.displayValue })),
  };
}

// ── survival curve ────────────────────────────────────────────────────────

export function buildSurvivalSpec(rows: AnalysisResultRow[], title: string): ChartSpec {
  const groups = Array.from(new Set(rows.map((r) => r.group_value)));
  const data: Data[] = groups.map((g, i) => {
    const points = rows.filter((r) => r.group_value === g);
    return {
      type: "scatter", mode: "lines", name: g === "_all_" ? title : g,
      x: points.map((p) => p.duration_days), y: points.map((p) => (p.value ?? 0) * 100),
      line: { shape: "hv", color: categoricalColor(i), width: 2 },
    };
  });
  return {
    data,
    layout: {
      hovermode: "x unified",
      xaxis: {
        title: { text: "Days" }, showspikes: true, spikemode: "across",
        spikedash: "dot", spikecolor: "#94a3b8", spikethickness: 1,
      },
      yaxis: { title: { text: "Survived %" }, range: [0, 100], gridcolor: "#e5e9f2" },
      showlegend: groups.length > 1,
    },
    summary: `Survival curve: ${title}. ` +
      rows.map((r) => `${r.group_value} @ ${r.duration_days}d: ${((r.value ?? 0) * 100).toFixed(0)}%`).join(", ") + ".",
    rows: rows.map((r) => ({
      key: `${r.group_value}_${r.duration_days}`, label: `${r.group_value === "_all_" ? title : r.group_value} @ ${r.duration_days}d`,
      text: `${((r.value ?? 0) * 100).toFixed(0)}% survived (at risk ${r.sample_size})`,
    })),
  };
}
