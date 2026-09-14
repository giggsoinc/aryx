import { Cloud, Loader2 } from "lucide-react";
import { PlotlyChart } from "@/components/planner/PlotlyChart";
import { WordCloudChart } from "@/components/planner/WordCloudChart";
import { buildAreaSpec, buildBarSpec, buildDonutSpec, type Fmt } from "@/lib/plotlySpecs";
import type { AnalysisResultRow, DocumentEntity, TimelinePoint } from "@/lib/types";

interface Props {
  workspaceId: number;
  hasUnstructured: boolean | null;
  wordCloud: DocumentEntity[] | null;
  timeline: TimelinePoint[] | null;
}

// Minimum distinct document-sourced entities before the word cloud renders
// instead of a "not enough content yet" empty state — a product judgment
// call (Priya), not derived from data. Tune once real workspaces exist.
const MIN_ENTITIES_FOR_WORD_CLOUD = 5;

const countFmt: Fmt = (v) => (v === null ? "—" : Math.round(v).toLocaleString());

// A bare group_value/value pair — every other AnalysisResultRow field is
// null since buildBarSpec/buildDonutSpec never read them. This reuses the
// structured dashboard's own chart builders on document-derived counts,
// entirely client-side — no new backend call beyond the word-cloud fetch
// DashboardRenderer already makes.
function countRow(group_value: string, value: number): AnalysisResultRow {
  return {
    group_value, value, numerator: null, denominator: null, sample_size: value,
    min: null, q1: null, q3: null, max: null, group_value_secondary: null,
    x: null, y: null, size: null, start: null, end: null, duration_days: null,
    buckets: null,
  };
}

/** Sum mention counts per ontology_type — "what kinds of things are in these
 *  documents" at a glance. */
function entityTypeBreakdown(entities: DocumentEntity[]): AnalysisResultRow[] {
  const totals = new Map<string, number>();
  for (const e of entities) totals.set(e.ontology_type, (totals.get(e.ontology_type) ?? 0) + e.count);
  return Array.from(totals.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => countRow(type, count));
}

/** Top N individual entities by mention count — same ranking as the word
 *  cloud (backend already orders by count desc), just a precise chart
 *  instead of font-size-scaled text. */
function topEntityRows(entities: DocumentEntity[], limit = 12): AnalysisResultRow[] {
  return entities.slice(0, limit).map((e) => countRow(e.name, e.count));
}

/** Entities discovered per day — a plain count over aryx_entity.created_at,
 *  not an activity/usage metric. A batch-ingested workspace legitimately
 *  shows one spike, not a trend; that's expected, not a bug. */
function timelineRows(points: TimelinePoint[]): AnalysisResultRow[] {
  return points.map((p) => countRow(p.date, p.count));
}

/** "Document Insights" — the unstructured-data half of the dashboard,
 *  outside the C07-C14 governed pipeline (see WordCloudChart.tsx). Pure
 *  presentational: DashboardRenderer owns the fetch/poll (bundled into its
 *  existing Promise.all so this never needs a second polling loop) and
 *  passes the results down as props. */
export function DocumentInsightsSection({ workspaceId, hasUnstructured, wordCloud, timeline }: Props) {
  if (!hasUnstructured) return null;
  return (
    <section className="mt-4 rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-2">
        <Cloud size={18} className="text-navy-500" />
        <h2 className="text-lg font-semibold text-navy-900">Document Insights</h2>
        {wordCloud === null && <Loader2 size={14} className="animate-spin text-navy-400" />}
      </div>
      <p className="mt-1 text-sm text-navy-500">
        What this workspace&apos;s ingested documents are about, drawn
        from entity mentions already extracted during ingestion — a
        plain frequency count, not an LLM summary. Click any term below
        to see sample quotes from the source documents.
      </p>
      {wordCloud !== null && wordCloud.length < MIN_ENTITIES_FOR_WORD_CLOUD && (
        <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
          Not enough document content yet to summarize — ingest a few
          more documents and this fills in on its own.
        </div>
      )}
      {wordCloud !== null && wordCloud.length >= MIN_ENTITIES_FOR_WORD_CLOUD && (
        <>
          <WordCloudChart workspaceId={workspaceId} entities={wordCloud} />
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-navy-100 bg-white p-4">
              <div className="text-xs font-medium uppercase text-navy-500">
                Entity types mentioned
              </div>
              <div className="mt-2">
                <PlotlyChart spec={buildDonutSpec(
                  entityTypeBreakdown(wordCloud), countFmt, "Entity types mentioned",
                )} />
              </div>
            </div>
            <div className="rounded-lg border border-navy-100 bg-white p-4">
              <div className="text-xs font-medium uppercase text-navy-500">
                Most-mentioned entities
              </div>
              <div className="mt-2">
                <PlotlyChart spec={buildBarSpec(
                  topEntityRows(wordCloud), countFmt, "Most-mentioned entities",
                )} />
              </div>
            </div>
          </div>
        </>
      )}
      {timeline !== null && timeline.length > 0 && (
        <div className="mt-4 rounded-lg border border-navy-100 bg-white p-4">
          <div className="text-xs font-medium uppercase text-navy-500">
            Entities discovered over time
          </div>
          <p className="mt-1 text-xs text-navy-400">
            Per-day count of document-sourced entities as they were first
            resolved — a discovery timeline, not an activity feed.
          </p>
          {timeline.length === 1 ? (
            // A one-point chart has no trend to show and, worse, an
            // actual dot-on-a-line renders as visually empty — a plain
            // stat says the same thing in a way that's actually
            // legible, instead of forcing a chart shape onto n=1.
            <div className="mt-3 rounded-lg bg-navy-50/40 px-4 py-3 text-sm text-navy-700">
              All <b>{timeline[0].count}</b> document-sourced entities
              were discovered on <b>{timeline[0].date}</b> — this
              workspace was ingested in a single batch. A trend line
              will appear here once documents are ingested across
              multiple days.
            </div>
          ) : (
            <div className="mt-2">
              <PlotlyChart spec={buildAreaSpec(
                timelineRows(timeline), countFmt, "Entities discovered over time",
              )} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
