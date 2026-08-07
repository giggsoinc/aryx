"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Gauge, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import type { Observability } from "@/lib/types";

/** Token consumption observability — the Ask tab has always logged its own
 *  usage (source="ask"); every other LLM call in the system (the dashboard
 *  planner, ontology mapping, resolution, tagging — everything routed
 *  through aryx.llm.complete_json/complete_text) now logs too, tagged
 *  source="pipeline". Without that split this panel would show only Ask
 *  usage and be silently blind to exactly the calls that hit rate limits
 *  and token-budget walls this session. */
export function ObservabilityPanel() {
  const { workspaceId } = useWorkspace();
  const [data, setData] = useState<Observability | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null); setErr(null);
    api.getObservability(workspaceId)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setErr(e instanceof Error ? e.message : "Failed to load"); });
    return () => { live = false; };
  }, [workspaceId]);

  if (err) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50/50 px-4 py-3 text-sm text-red-700">
        <AlertTriangle size={16} /> {err}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex items-center gap-2 px-4 py-6 text-sm text-subtle">
        <Loader2 size={15} className="animate-spin" /> Loading usage…
      </div>
    );
  }

  const llm = data.llm;
  const bySource = llm.by_source ?? [];

  return (
    <div className="space-y-6">
      <section>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-navy-900">
          <Gauge size={18} className="text-steel-600" /> Token Consumption
        </h2>
        <p className="mt-1 text-sm text-subtle">
          Every LLM call in the system — Ask, and every pipeline call (dashboard
          planner, ontology mapping, resolution, tagging) — logged here, split by
          source below.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Total tokens" value={fmt(llm.total_tokens)} />
        <StatTile label="Total calls" value={fmt(llm.total_calls)} />
        <StatTile label="Avg latency" value={llm.avg_latency_ms != null ? `${llm.avg_latency_ms} ms` : "—"} />
        <StatTile label="Current model" value={data.model_config.answer_model}
                  sub={`${data.model_config.provider}${data.model_config.api_key_set ? "" : " · no key set"}`} />
      </section>

      {bySource.length > 0 && (
        <section>
          <div className="mb-1.5 text-xs font-semibold uppercase text-navy-400">By source</div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {bySource.map((s) => (
              <div key={s.source} className="rounded-xl border border-navy-100 bg-white p-4">
                <div className="flex items-center justify-between">
                  <SourcePill source={s.source} />
                  <span className="text-xs text-navy-400">{s.total_calls} call{s.total_calls === 1 ? "" : "s"}</span>
                </div>
                <div className="mt-2 text-2xl font-semibold text-navy-900">{fmt(s.total_tokens)}</div>
                <div className="mt-0.5 text-xs text-subtle">
                  {fmt(s.prompt_tokens)} prompt · {fmt(s.completion_tokens)} completion ·{" "}
                  {s.avg_latency_ms} ms avg
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="mb-1.5 text-xs font-semibold uppercase text-navy-400">Recent calls</div>
        {data.llm_recent.length === 0 ? (
          <div className="rounded-xl border border-navy-100 px-4 py-3 text-sm text-subtle">
            No LLM calls logged yet.
          </div>
        ) : (
          <ul className="space-y-1">
            {data.llm_recent.map((c, i) => (
              <li key={i}
                  className="flex flex-wrap items-center gap-3 rounded-lg border border-navy-100 px-3 py-1.5 text-[13px]">
                <SourcePill source={c.source} />
                <span className="font-medium text-navy-700">{c.model}</span>
                <span className="text-navy-500">{c.role}</span>
                <span className="text-navy-500">
                  {fmt(c.prompt_tokens + c.completion_tokens)} tokens
                </span>
                <span className="text-navy-400">{c.latency_ms} ms</span>
                {c.error && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                    {c.error}
                  </span>
                )}
                <span className="ml-auto text-xs text-navy-400">
                  {new Date(c.ts).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function fmt(n: number | undefined): string {
  return n != null ? n.toLocaleString() : "—";
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-navy-100 bg-white p-4">
      <div className="text-xs font-semibold uppercase text-navy-400">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold text-navy-900" title={value}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-subtle" title={sub}>{sub}</div>}
    </div>
  );
}

function SourcePill({ source }: { source: string }) {
  const cls = source === "ask" ? "bg-steel-100 text-steel-700" : "bg-navy-100 text-navy-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{source}</span>;
}
