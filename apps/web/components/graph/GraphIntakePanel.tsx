"use client";

import { useEffect, useState } from "react";
import {
  Loader2, Share2, CheckCircle2, XCircle, RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import type { GraphIntakeResult, GraphProfile } from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** C05 — Knowledge Graph Intake & Validation. Read-only view of validated,
 *  versioned graph snapshots auto-derived from the workspace's Aryx graph,
 *  with a manual re-validate action. */
export function GraphIntakePanel({ workspaceId }: Props) {
  const [rows, setRows] = useState<GraphIntakeResult[]>([]);
  const [profile, setProfile] = useState<GraphProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = () => {
    api.listGraphVersions(workspaceId)
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
    api.getGraphProfile(workspaceId).then(setProfile).catch(() => setProfile(null));
  };
  // Live-refresh: C05/C06 compute in the background once intent (C01) is
  // valid, so poll instead of requiring the manual "Re-validate" click.
  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [workspaceId]);

  const run = async () => {
    setRunning(true);
    try {
      await api.runGraphIntake(workspaceId);
      load();
    } catch {
      /* no entities yet, etc. */
    } finally {
      setRunning(false);
    }
  };

  const latest = rows[0];

  return (
    <div className="mx-auto max-w-6xl px-6 pb-8">
      <section className="rounded-xl border border-navy-100 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Share2 size={18} className="text-navy-500" />
            <h2 className="text-lg font-semibold text-navy-900">Knowledge Graph Intake</h2>
            {loading && <Loader2 size={14} className="animate-spin text-navy-400" />}
          </div>
          <button onClick={run} disabled={running}
                  className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-navy-200 px-3 py-1.5 text-sm text-navy-700 hover:bg-navy-50 disabled:opacity-60">
            {running ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Re-validate graph
          </button>
        </div>
        <p className="mt-1 text-sm text-navy-500">
          The Aryx graph is auto-derived from this workspace’s entities and
          relationships, validated, and stored as an immutable version before
          graph analysis is allowed.
        </p>

        {latest && (
          <div className={`mt-4 rounded-lg border p-4 ${latest.schema_status === "valid" ? "border-emerald-200 bg-emerald-50/40" : "border-red-200 bg-red-50/40"}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-semibold text-navy-900">
                {latest.schema_status === "valid"
                  ? <CheckCircle2 size={17} className="text-emerald-600" />
                  : <XCircle size={17} className="text-red-600" />}
                {latest.graph_id} · {latest.graph_version}
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${latest.schema_status === "valid" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                  {latest.schema_status}
                </span>
              </div>
              <code className="text-xs text-navy-400">{latest.normalized_graph_ref}</code>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-5">
              <Stat label="Entities" value={latest.entity_count} />
              <Stat label="Relationships" value={latest.relationship_count} />
              <Stat label="Duplicate entities" value={latest.duplicate_entities} warn />
              <Stat label="Dangling rels" value={latest.dangling_relationships} warn />
              <Stat label="Duplicate rels" value={latest.duplicate_relationships} warn />
            </div>
            {latest.issues.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">
                {latest.issues.slice(0, 12).map((iss, i) => (
                  <span key={i} title={iss.detail}
                        className="rounded bg-red-50 px-2 py-0.5 text-xs text-red-700">
                    {iss.code}
                  </span>
                ))}
                {latest.issues.length > 12 && (
                  <span className="text-xs text-navy-400">+{latest.issues.length - 12} more</span>
                )}
              </div>
            )}
          </div>
        )}

        {profile && <GraphProfileView profile={profile} />}

        {rows.length === 0 && !loading && (
          <div className="mt-6 rounded-lg border border-dashed border-navy-200 px-4 py-10 text-center text-sm text-navy-400">
            No graph yet — ingest data so entities and relationships exist, then
            the graph is validated automatically.
          </div>
        )}

        {rows.length > 1 && (
          <div className="mt-4">
            <div className="mb-1 text-xs font-semibold uppercase text-navy-400">
              Version history
            </div>
            <ul className="space-y-1">
              {rows.map((r) => (
                <li key={`${r.graph_id}/${r.graph_version}`}
                    className="flex items-center gap-3 rounded-lg border border-navy-100 px-3 py-1.5 text-sm">
                  <span className="font-medium text-navy-700">{r.graph_version}</span>
                  <span className="text-navy-500">{r.entity_count} entities · {r.relationship_count} rels</span>
                  <span className={`ml-auto rounded-full px-2 py-0.5 text-xs font-medium ${r.schema_status === "valid" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                    {r.schema_status}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

function GraphProfileView({ profile }: { profile: GraphProfile }) {
  return (
    <div className="mt-4 rounded-lg border border-navy-100 bg-navy-50/30 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm font-semibold text-navy-800">
        Graph profile
        <span className="rounded bg-navy-100 px-1.5 py-0.5 text-xs font-normal text-navy-500">
          {profile.graph_version}
        </span>
        {profile.user_objective && (
          <span className="ml-auto max-w-md truncate text-xs font-normal text-navy-400"
                title={profile.user_objective}>
            objective: {profile.user_objective}
          </span>
        )}
      </div>

      {/* Entity types */}
      <div className="mb-3">
        <div className="mb-1 text-xs font-semibold uppercase text-navy-400">Entity types</div>
        <div className="flex flex-wrap gap-1.5">
          {profile.entity_types.map((t) => (
            <span key={t.type} className="rounded bg-white px-2 py-0.5 text-xs text-navy-700 ring-1 ring-navy-100">
              {t.type} <span className="text-navy-400">· {t.count.toLocaleString()}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Schema summary */}
      {profile.schema_edges.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-xs font-semibold uppercase text-navy-400">Schema</div>
          <div className="flex flex-wrap gap-1.5">
            {profile.schema_edges.map((e, i) => (
              <span key={i} className="rounded bg-white px-2 py-0.5 font-mono text-xs text-navy-600 ring-1 ring-navy-100">
                {e.source_type} <span className="text-sky-600">—{e.relationship}→</span> {e.target_type}
                <span className="text-navy-300"> ({e.count.toLocaleString()})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Verified paths */}
      <div>
        <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase text-navy-400">
          Verified paths
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium normal-case text-emerald-700">
            {profile.verified_paths.length} · depth ≤ {profile.maximum_path_depth}
          </span>
        </div>
        {profile.verified_paths.length === 0 && (
          <p className="text-xs text-navy-400">No multi-hop paths in this graph.</p>
        )}
        <ul className="space-y-1">
          {profile.verified_paths.slice(0, 12).map((vp) => (
            <li key={vp.path_id} className="flex items-center gap-1 overflow-x-auto text-xs">
              {vp.path.map((seg, i) => (
                <span key={i} className={i % 2 === 0
                  ? "whitespace-nowrap rounded bg-white px-1.5 py-0.5 font-medium text-navy-800 ring-1 ring-navy-100"
                  : "whitespace-nowrap px-1 text-sky-600"}>
                  {i % 2 === 0 ? seg : `—${seg}→`}
                </span>
              ))}
              <span className="ml-1 text-navy-300">d{vp.depth}</span>
            </li>
          ))}
        </ul>
      </div>

      {profile.quality_flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {profile.quality_flags.map((f, i) => (
            <span key={i} title={f.detail} className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
              {f.code}{f.type ? `: ${f.type}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div>
      <div className={`text-lg font-semibold ${warn && value > 0 ? "text-amber-700" : "text-navy-900"}`}>{value}</div>
      <div className="text-xs text-navy-500">{label}</div>
    </div>
  );
}
