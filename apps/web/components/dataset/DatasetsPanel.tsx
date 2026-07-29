"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Loader2, Database, ArrowRight, ChevronRight, ChevronDown, AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  DatasetIngestResult, DatasetProfile, SemanticProfile, PlanningContext,
} from "@/lib/types";

interface Props {
  workspaceId: number;
}

const ROLE_CLS: Record<string, string> = {
  identifier: "bg-violet-100 text-violet-700",
  measure: "bg-emerald-100 text-emerald-700",
  dimension: "bg-sky-100 text-sky-700",
  time: "bg-amber-100 text-amber-700",
  status: "bg-rose-100 text-rose-700",
  attribute: "bg-navy-100 text-navy-600",
};

/** Read-only view of datasets ingested via Onboard (C02), each expandable to
 *  its deterministic profile (C03): column types, analytical roles, and
 *  quality flags. Uploads happen in Onboard, not here. */
export function DatasetsPanel({ workspaceId }: Props) {
  const [rows, setRows] = useState<DatasetIngestResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<Record<string, DatasetProfile | "loading" | "none">>({});
  const [semantics, setSemantics] = useState<Record<string, SemanticProfile | "loading" | "none">>({});
  const [contexts, setContexts] = useState<Record<string, PlanningContext | "none">>({});
  const openRef = useRef<string | null>(null);
  const profilesRef = useRef(profiles);
  const semanticsRef = useRef(semantics);
  useEffect(() => { openRef.current = open; }, [open]);
  useEffect(() => { profilesRef.current = profiles; }, [profiles]);
  useEffect(() => { semanticsRef.current = semantics; }, [semantics]);

  // Fetches C03/C04/C07 for one dataset. Backend computation is deferred
  // until intent (C01) is valid, so a fresh dataset may show "none" for a
  // while — retried automatically by the poll below until it resolves.
  const loadDetail = (datasetId: string) => {
    setProfiles((p) => ({ ...p, [datasetId]: "loading" }));
    api.getProfile(datasetId, workspaceId)
      .then((prof) => setProfiles((p) => ({ ...p, [datasetId]: prof })))
      .catch(() => setProfiles((p) => ({ ...p, [datasetId]: "none" })));
    setSemantics((s) => ({ ...s, [datasetId]: "loading" }));
    api.getSemantic(datasetId, workspaceId)
      .then((sem) => setSemantics((s) => ({ ...s, [datasetId]: sem })))
      .catch(() => setSemantics((s) => ({ ...s, [datasetId]: "none" })));
    api.getPlanningContext(datasetId, workspaceId)
      .then((ctx) => setContexts((c) => ({ ...c, [datasetId]: ctx })))
      .catch(() => setContexts((c) => ({ ...c, [datasetId]: "none" })));
  };

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await api.listDatasetVersions(workspaceId);
        if (alive) setRows(data);
      } catch {
        if (alive) setRows([]);
      } finally {
        if (alive) setLoading(false);
      }
      // Live-refresh: while the open row's profile/semantic hasn't resolved
      // yet (still pending on C01, or backend still computing), keep polling
      // it instead of requiring a manual re-expand.
      const openId = openRef.current;
      if (alive && openId) {
        const prof = profilesRef.current[openId];
        const sem = semanticsRef.current[openId];
        const pending = (v: unknown) => v === undefined || v === "loading" || v === "none";
        if (pending(prof) || pending(sem)) {
          loadDetail(openId);
        }
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [workspaceId]);

  const toggle = (datasetId: string) => {
    if (open === datasetId) { setOpen(null); return; }
    setOpen(datasetId);
    if (!profiles[datasetId]) {
      loadDetail(datasetId);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database size={18} className="text-navy-500" />
            <h2 className="text-lg font-semibold text-navy-900">Datasets &amp; Profiles</h2>
            {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
          </div>
          <Link href="/start"
                className="focus-ring inline-flex items-center gap-1 rounded-lg border border-navy-200 px-3 py-1.5 text-sm text-navy-700 hover:bg-navy-50">
            Upload in Onboard <ArrowRight size={13} />
          </Link>
        </div>
        <p className="mt-1 text-sm text-navy-500">
          Immutable, versioned snapshots from Onboard. Click a row to see its
          deterministic profile — column types, analytical roles, and quality flags.
        </p>

        {rows.length === 0 && !loading && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            No datasets yet. Upload files in{" "}
            <Link href="/start" className="text-navy-700 underline">Onboard</Link>.
          </div>
        )}

        {rows.length > 0 && (
          <div className="mt-4 divide-y divide-navy-50">
            {rows.map((r) => {
              const isOpen = open === r.dataset_id;
              const prof = profiles[r.dataset_id];
              return (
                <div key={`${r.dataset_id}/${r.dataset_version}`}>
                  <button onClick={() => toggle(r.dataset_id)}
                          className="flex w-full items-center gap-3 py-2.5 text-left text-sm hover:bg-navy-50/50">
                    {isOpen ? <ChevronDown size={15} className="text-navy-400" />
                            : <ChevronRight size={15} className="text-navy-400" />}
                    <span className="flex-1 font-medium text-navy-900">{r.dataset_id}</span>
                    <span className="text-navy-500">{r.dataset_version}</span>
                    <span className="w-16 text-navy-500">{r.format}</span>
                    <span className="w-20 text-navy-500">{r.row_count_estimate} rows</span>
                    <IngestPill status={r.ingestion_status} />
                    <ProcPill status={r.processing_status} />
                  </button>
                  {isOpen && (
                    <div className="pb-4 pl-8">
                      {prof === "loading" && (
                        <div className="flex items-center gap-2 py-3 text-sm text-navy-400">
                          <Loader2 size={13} className="animate-spin" /> Loading profile…
                        </div>
                      )}
                      {prof === "none" && (
                        <p className="py-3 text-sm text-navy-400">No profile available.</p>
                      )}
                      {prof && prof !== "loading" && prof !== "none" && (
                        <ProfileView profile={prof} />
                      )}
                      {(() => {
                        const sem = semantics[r.dataset_id];
                        if (sem && sem !== "loading" && sem !== "none") {
                          return <SemanticView semantic={sem} />;
                        }
                        return null;
                      })()}
                      {(() => {
                        const ctx = contexts[r.dataset_id];
                        if (ctx && ctx !== "none") {
                          return <PlanningContextView context={ctx} />;
                        }
                        return null;
                      })()}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function ProfileView({ profile }: { profile: DatasetProfile }) {
  return (
    <div className="mt-2 rounded-lg border border-navy-100 bg-navy-50/30 p-4">
      <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-navy-500">
        <span><b className="text-navy-800">{profile.row_count}</b> rows</span>
        <span><b className="text-navy-800">{profile.column_count}</b> columns</span>
        <span><b className="text-navy-800">{profile.duplicate_row_count}</b> duplicate rows</span>
        <span><b className="text-navy-800">{profile.quality_flags.length}</b> quality flags</span>
        <code className="text-navy-400">{profile.dataset_profile_id}</code>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="uppercase text-navy-400">
            <tr className="border-b border-navy-100">
              <th className="py-1.5 pr-3">Column</th>
              <th className="py-1.5 pr-3">Canonical type</th>
              <th className="py-1.5 pr-3">Role</th>
              <th className="py-1.5 pr-3">Nulls</th>
              <th className="py-1.5 pr-3">Unique</th>
              <th className="py-1.5">Samples</th>
            </tr>
          </thead>
          <tbody>
            {profile.columns.map((c) => (
              <tr key={c.name} className="border-b border-navy-50 last:border-0">
                <td className="py-1.5 pr-3 font-medium text-navy-900">{c.name}</td>
                <td className="py-1.5 pr-3 text-navy-600">{c.canonical_type}</td>
                <td className="py-1.5 pr-3">
                  <span className={`rounded px-1.5 py-0.5 font-medium ${ROLE_CLS[c.candidate_role] ?? "bg-navy-100 text-navy-600"}`}>
                    {c.candidate_role}
                  </span>
                </td>
                <td className={`py-1.5 pr-3 ${c.null_count > 0 ? "text-amber-700" : "text-navy-500"}`}>{c.null_count}</td>
                <td className="py-1.5 pr-3 text-navy-500">{c.unique_count}</td>
                <td className="py-1.5 text-navy-400">
                  {c.sample_values.slice(0, 4).join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {profile.quality_flags.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-navy-700">
            <AlertTriangle size={12} className="text-amber-500" /> Quality flags
          </div>
          <div className="flex flex-wrap gap-1">
            {profile.quality_flags.map((f, i) => (
              <span key={i} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
                {f.column}: {f.code}{f.count ? ` (${f.count})` : ""}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PlanningContextView({ context }: { context: PlanningContext }) {
  const statusCls = context.context_status === "complete" ? "bg-emerald-100 text-emerald-700"
    : context.context_status === "blocked" ? "bg-red-100 text-red-700"
    : "bg-amber-100 text-amber-700";
  return (
    <div className="mt-2 rounded-lg border border-navy-100 bg-white p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-navy-800">
        Planning context
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusCls}`}>
          {context.context_status}
        </span>
        <span className="text-xs font-normal text-navy-400">
          smallest approved package
        </span>
        {context.objective && (
          <span className="ml-auto max-w-xs truncate text-xs font-normal text-navy-400"
                title={context.objective}>obj: {context.objective}</span>
        )}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
            Approved columns ({context.approved_columns.length})
          </div>
          <div className="flex flex-wrap gap-1">
            {context.approved_columns.map((c) => (
              <span key={c.name} className="rounded bg-navy-50 px-1.5 py-0.5 text-xs text-navy-700">
                {c.name} <span className="text-navy-400">· {c.type}</span>
              </span>
            ))}
          </div>
          {context.approved_graph_paths.length > 0 && (
            <div className="mt-2">
              <div className="mb-1 text-xs font-semibold uppercase text-navy-400">Approved paths</div>
              <div className="flex flex-wrap gap-1">
                {context.approved_graph_paths.map((p) => (
                  <span key={p} className="rounded bg-white px-1.5 py-0.5 font-mono text-xs text-navy-600 ring-1 ring-navy-100">{p}</span>
                ))}
              </div>
            </div>
          )}
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
            Supported operations ({context.supported_operations.length})
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            {context.supported_operations.map((op) => (
              <span key={op} className="rounded bg-sky-50 px-1.5 py-0.5 text-xs text-sky-700">{op}</span>
            ))}
          </div>
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
            Supported charts ({context.supported_charts.length})
          </div>
          <div className="flex flex-wrap gap-1">
            {context.supported_charts.map((ch) => (
              <span key={ch} className="rounded bg-violet-50 px-1.5 py-0.5 text-xs text-violet-700">{ch}</span>
            ))}
          </div>
        </div>
      </div>

      {context.warnings.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {context.warnings.map((w, i) => (
            <span key={i} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">{w}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function SemanticView({ semantic }: { semantic: SemanticProfile }) {
  return (
    <div className="mt-2 rounded-lg border border-navy-100 bg-white p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-navy-800">
        Semantic mapping
        <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
          {semantic.annotations.length} grounded
        </span>
        {semantic.unresolved_fields.length > 0 && (
          <span className="rounded bg-navy-100 px-1.5 py-0.5 text-xs font-medium text-navy-600">
            {semantic.unresolved_fields.length} unresolved
          </span>
        )}
        {semantic.domain && (
          <span className="ml-auto text-xs font-normal text-navy-400">domain: {semantic.domain}</span>
        )}
      </div>

      {semantic.annotations.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="uppercase text-navy-400">
              <tr className="border-b border-navy-100">
                <th className="py-1.5 pr-3">Column</th>
                <th className="py-1.5 pr-3">Business concept</th>
                <th className="py-1.5 pr-3">Confidence</th>
                <th className="py-1.5">Provenance (ontology)</th>
              </tr>
            </thead>
            <tbody>
              {semantic.annotations.map((a) => (
                <tr key={a.column} className="border-b border-navy-50 last:border-0">
                  <td className="py-1.5 pr-3 font-medium text-navy-900">{a.column}</td>
                  <td className="py-1.5 pr-3 text-navy-700">
                    <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-800">{a.business_concept}</span>
                  </td>
                  <td className="py-1.5 pr-3">
                    <ConfidenceBar value={a.confidence} />
                  </td>
                  <td className="py-1.5 text-navy-400">
                    {a.ontology_type}{a.ontology_attribute ? ` · ${a.ontology_attribute}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {semantic.unresolved_fields.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-semibold text-navy-500">
            Unresolved (left unmapped rather than guessed)
          </div>
          <div className="flex flex-wrap gap-1">
            {semantic.unresolved_fields.map((u) => (
              <span key={u.column} title={u.reason}
                    className="rounded bg-navy-50 px-2 py-0.5 text-xs text-navy-500">
                {u.column} <span className="text-navy-300">({u.best_confidence.toFixed(2)})</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const cls = value >= 0.85 ? "bg-emerald-500" : value >= 0.6 ? "bg-sky-500" : "bg-amber-500";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-navy-100">
        <span className={`block h-full ${cls}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-navy-500">{pct}%</span>
    </span>
  );
}

function IngestPill({ status }: { status: DatasetIngestResult["ingestion_status"] }) {
  const cls = status === "rejected" ? "bg-red-100 text-red-700"
    : status === "duplicate" ? "bg-amber-100 text-amber-700"
    : "bg-emerald-100 text-emerald-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

function ProcPill({ status }: { status: string }) {
  const running = status === "queued" || status === "running";
  const cls = status === "failed" ? "bg-red-100 text-red-700"
    : status === "complete" ? "bg-emerald-100 text-emerald-700"
    : "bg-sky-100 text-sky-700";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {running && <Loader2 size={11} className="animate-spin" />}
      {status}
    </span>
  );
}
