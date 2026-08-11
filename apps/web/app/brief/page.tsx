"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Database, FileText } from "lucide-react";
import { Header } from "@/components/brand/Header";
import { BriefBuilder } from "@/components/brief/BriefBuilder";
import { useWorkspace } from "@/lib/workspace";
import type { Brief } from "@/lib/types";

/** Revisit/edit surface for the workspace brief. */
export default function BriefPage() {
  const { workspaceId, workspaces, setWorkspaceId, refresh } = useWorkspace();
  const [savedAt, setSavedAt] = useState(0);

  const initial = useMemo<Brief>(() => {
    const ws = workspaces.find((w) => w.id === workspaceId);
    return (ws?.brief ?? {}) as Brief;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, workspaces, savedAt]);

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-3xl px-6 pb-8 pt-6">
          {/* Product path: Brief is step 1; data load is step 2 (setup wizard). */}
          <div className="mb-6 rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
              Getting started
            </div>
            <ol className="mt-3 space-y-2 text-[13px] text-navy-800">
              <li className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-navy-800 text-[11px] font-bold text-white">
                  1
                </span>
                <span>
                  <b>Add your brief</b> — answer the six questions below (or
                  draft with AI). This steers what Aryx looks for in your data.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-steel-500 text-[11px] font-bold text-white">
                  2
                </span>
                <span>
                  <b>Add your data</b> — load tables or files so the graph has
                  something to resolve.{" "}
                  <Link
                    href="/start"
                    className="inline-flex items-center gap-1 font-semibold text-steel-600 underline hover:text-navy-800"
                  >
                    <Database size={13} /> Open setup — load data
                  </Link>
                </span>
              </li>
            </ol>
            <p className="mt-3 text-[11px] text-subtle">
              There is no separate “Ingest” tab yet in Lite — loading data is
              the setup wizard. After data lands, explore it on{" "}
              <Link href="/data" className="underline">Data</Link>.
            </p>
          </div>

          <div className="mb-6 flex items-center gap-2">
            <FileText size={20} className="text-steel-600" />
            <div>
              <h1 className="font-display text-2xl font-bold text-navy-900">
                Step 1 · Brief
              </h1>
              <p className="text-[13px] text-subtle">
                Six questions that ground every extraction. Answer by hand, or
                optionally draft with AI. Skip any — Aryx ingests more generically.
              </p>
            </div>
          </div>
          <BriefBuilder
            workspaceId={workspaceId}
            initial={initial}
            submitLabel="Save Brief"
            onSubmitted={async () => {
              await refresh();
              setSavedAt(Date.now());
            }}
          />

          <div className="mt-6 rounded-xl border border-dashed border-steel-400/50 bg-white/80 px-4 py-3 text-[13px] text-navy-800">
            <b>Next — Step 2 · Add your data</b>
            <p className="mt-1 text-[12px] text-subtle">
              After you save the brief, load a database and/or files so Aryx can
              build entities. Choose <b>Database</b> or <b>Files</b> in setup.
              “Types only (no data yet)” means skip loading and define types later
              on Model — it does <em>not</em> mean type individual records by hand.
            </p>
            <Link
              href="/start"
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-navy-700"
            >
              <Database size={14} /> Go to setup — add data
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
