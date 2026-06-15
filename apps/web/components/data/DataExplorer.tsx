"use client";

import { useEffect, useState } from "react";
import { Database, ListTree, Loader2, Network, Table2 } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import type { DataSummary } from "@/lib/types";
import { GraphLens } from "./GraphLens";
import { SummaryStrip } from "./SummaryStrip";
import { TreeLens } from "./TreeLens";

type Lens = "tree" | "graph";

/** The Data tab: transparency over the workspace's resolved entities.
 *  Slice 1 ships the Tree lens; Table + Graph follow. */
export function DataExplorer() {
  const { workspaceId } = useWorkspace();
  const [summary, setSummary] = useState<DataSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lens, setLens] = useState<Lens>("tree");

  useEffect(() => {
    let live = true;
    setSummary(null); setErr(null);
    api.dataSummary(workspaceId)
      .then((d) => { if (live) ("error" in d && d.error) ? setErr(d.error) : setSummary(d); })
      .catch((e) => { if (live) setErr(e instanceof Error ? e.message : "failed"); });
    return () => { live = false; };
  }, [workspaceId]);

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <div className="flex items-center gap-2 text-steel-600">
        <Database size={18} />
        <span className="text-[11px] font-bold uppercase tracking-[0.16em]">Data</span>
      </div>
      <h1 className="mt-2 font-display text-3xl text-navy-900">Where your data lives.</h1>
      <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-subtle">
        Every entity Aryx resolved, what type it is, and the exact source record
        it came from — nothing hidden in a database you can&apos;t see.
      </p>

      {err && (
        <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-[13px] text-rose-700">
          {err}
        </div>
      )}

      {!summary && !err && (
        <div className="mt-8 flex items-center gap-2 text-[13px] text-subtle">
          <Loader2 size={15} className="animate-spin" /> Reading the workspace…
        </div>
      )}

      {summary && (
        <div className="mt-6 space-y-5">
          <SummaryStrip summary={summary} />

          <div className="flex items-center gap-1 border-b border-navy-100">
            <Tab icon={<ListTree size={15} />} label="Tree"
                 active={lens === "tree"} onClick={() => setLens("tree")} />
            <Tab icon={<Network size={15} />} label="Graph"
                 active={lens === "graph"} onClick={() => setLens("graph")} />
            <Soon icon={<Table2 size={15} />} label="Table" />
          </div>

          {lens === "tree" ? <TreeLens types={summary.types} /> : <GraphLens />}
        </div>
      )}
    </div>
  );
}

function Tab({ icon, label, active, onClick }: {
  icon: React.ReactNode; label: string; active: boolean; onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick}
      className={"flex items-center gap-1.5 border-b-2 px-4 py-2 text-[13px] font-semibold " +
        (active ? "border-steel-500 text-navy-900"
                : "border-transparent text-subtle hover:text-navy-700")}>
      {icon} {label}
    </button>
  );
}

function Soon({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="flex cursor-default items-center gap-1.5 px-4 py-2 text-[13px] font-medium text-navy-300">
      {icon} {label}
      <span className="rounded-full bg-navy-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-navy-400">
        soon
      </span>
    </span>
  );
}
