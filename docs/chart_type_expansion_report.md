# Report: replacing primitive bar-everywhere charts with real chart types

## The issue

The user's reference dashboard (`contract_charts/index.html`, a Plotly export)
has 29 real chart types — sankey, waterfall, treemap, sunburst, gantt, radar,
box, pareto, calendar heatmap, survival curves, etc. The Aryx workspace
dashboard, by contrast, renders almost everything as a bar chart, even when
the requested `chart_type` was `line`, `scatter`, or `donut`.

Investigation found three independent root causes, not one:

1. **Backend data-shape ceiling.** C12's `AnalysisResultRow` is always one
   flat `{group_value, value, sample_size}` per category. That shape can
   only ever drive a bar/line/donut/box — it structurally cannot carry a
   hierarchy (treemap/sunburst), a flow/crosstab (sankey/heatmap), raw
   per-row points (scatter/bubble/gantt), or a computed curve (survival
   curve). No frontend fix could have solved this; the execution layer
   itself needed new operations and result shapes.
2. **Frontend rendering ceiling.** `DashboardRenderer.tsx` renders `bar`,
   `line`, `scatter`, and `donut` through the exact same Recharts
   `BarChart` component — by the code's own comment, "a faithful (not
   decorative) simplification," i.e. `scatter` and `line` were already
   fake, always rendered as bars. Recharts has no native sankey/
   treemap/sunburst; `box_plot` already needed a hand-drawn-SVG-shape
   hack just to fake a box plot. This does not scale to real chart
   topologies.
3. **No shape guidance for the planner LLM.** The planner prompt hands the
   model a flat whitelist of chart types and lets it guess, with zero
   guidance on which chart type fits which data shape. This is the direct,
   mechanical cause of "everything becomes a bar chart" — nothing ever
   told it not to.

## What we're doing about it

Agreed with the user on two irreversible-ish decisions before touching
code: adopt **Plotly.js** (`react-plotly.js`) as the one charting engine for
every chart type (matches the reference exactly; one generic component
instead of N bespoke Recharts hacks), and go **full scope** now — add real
operations/result shapes for every new chart family rather than phasing.

The design collapses the 29 reference types into a small number of new,
reusable data shapes (see the full plan for the complete mapping):

| New `Analysis.operation` | Shape it produces | Powers |
|---|---|---|
| `crosstab` | flat `(group, group_2) -> value` cells | sankey, treemap, sunburst, heatmap_matrix, calendar_heatmap |
| `row_points` | raw per-row `(x, y, size?)` | scatter (now real), bubble |
| `date_span` | raw per-row `(label, start, end)` | gantt |
| `survival` | Kaplan-Meier `(duration, survived_fraction, at_risk)` | survival curve |
| `histogram` | `{bucket_start, bucket_end, count}[]` | histogram |

Waterfall, pareto, area, step, and slopegraph need **no backend change** —
they're new Plotly trace types drawn over data the pipeline already
produces today.

Every addition follows the codebase's existing "no invention" discipline:
new entries in the governed catalogue whitelist, deterministic grounding
that drops (never invents) unapproved references, fixed execution
templates, and new structural validation rules — the same pattern already
used for `box_plot`/`grouped_bar`, just repeated for each new shape.

The full technical plan (exact fields, templates, and file list) is saved
at `~/.claude/plans/drifting-bubbling-hopper.md` and was reviewed/approved
before implementation started.

## Progress so far

Backend, in order:
- [x] `planning/catalogues.py` — new operations + chart types added to the
      governed whitelist.
- [x] `andie_planner/models.py` — `Analysis` gained `x_column`/`y_column`/
      `size_column`/`start_column`/`end_column`; `Visualization` gained
      `axis_refs` (radar).
- [x] `andie_planner/ground.py` — the new fields are grounded (dropped with
      a warning if not an approved column/ref), never trusted from the LLM
      directly.
- [x] `execution_compiler/templates.py` + `compile.py` — new vetted
      templates (`grouped2d_*`, `row_points`, `row_date_spans`,
      `survival_curve`, `histogram_buckets_numeric` + grouped variant) and
      the compiler branches that bind them.
- [x] `analysis_execution/models.py` — `AnalysisResultRow` gained the new
      optional fields (mirrors the existing `min`/`q1`/`q3`/`max` convention).
- [x] `analysis_execution/execute.py` — the actual computation for every
      new template, including a hand-verifiable Kaplan-Meier survival
      estimator (the single most novel piece of this change).
- [x] `analysis_execution/run.py` — unpacks each new result shape into
      `AnalysisResultRow`s, dispatching on `Analysis.operation` rather than
      guessing from the shape.

- [x] `spec_validation/checks.py` — structural axis-compatibility rules per
      new chart type (crosstab, row_points, date_span, survival, histogram,
      radar), all folded into check 8 (still 10 named checks total).
- [x] `andie_planner/prompt.py` — the actual fix for "why does everything
      become a bar chart": a chart-type-to-data-shape guide added to the
      system prompt.
- [x] `dashboard_composition` — `axis_refs` threaded through composition.
- [x] Backend tests for every new template/branch, including a
      hand-computed survival-curve test (4-row worked example, exact
      expected fractions asserted). Full backend suite: 412 passed (two
      pre-existing, unrelated failures excluded — see below).
- [x] Frontend: added `react-plotly.js` + `plotly.js-dist-min`, built
      `PlotlyChart.tsx` + `plotlySpecs.ts` (one builder per chart type,
      palette validated with the dataviz skill's script rather than
      eyeballed), migrated `DashboardRenderer.tsx`'s dispatch, deleted the
      superseded Recharts components (`BarChart.tsx`, `BoxPlotChart.tsx`,
      `GroupedBarChart.tsx`) and the now-unused `recharts` dependency,
      mirrored every model change into `apps/web/lib/types.ts`.
- [x] `npm run build` — passes (had to fix: a `plotly.js-dist-min` type
      shim, and a client-only dynamic import for Plotly since it touches
      `self`/`window` at module load and broke Next's server prerender).

## Pre-existing issues found, not caused by this change

- `tests/test_actions.py` stubs `sys.modules["psycopg"]` for its own
  isolated testing; that stub leaks into `sys.modules` for the rest of the
  pytest process, breaking any later test file's real
  `from psycopg.errors import ...` import. Reproduces on `main` before this
  change too — a test-isolation bug, not something touched here.
- `tests/test_ports_seam.py` fails two Settings-validation tests because
  the local `.env` has extra fields (`postgres_password`,
  `aryx_llm_provider`, etc.) the `Settings` pydantic model now rejects as
  `extra_forbidden` — an environment/config drift issue, unrelated to
  chart types.

Both were confirmed unrelated by inspection (neither file references
charts, analyses, or anything this change touched) and by isolating them
from the rest of the suite, which passes cleanly.

This report reflects the finished state of the implementation described
above; the plan file and the actual code remain authoritative for exact
details.
