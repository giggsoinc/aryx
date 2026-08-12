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
          <div className="mb-6 rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
              Getting started · data first
            </div>
            <ol className="mt-3 space-y-2 text-[13px] text-navy-800">
              <li className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-navy-800 text-[11px] font-bold text-white">
                  1
                </span>
                <span>
                  <b>Load your data</b> — setup wizard samples files/DB first.{" "}
                  <Link
                    href="/start"
                    className="inline-flex items-center gap-1 font-semibold text-steel-600 underline hover:text-navy-800"
                  >
                    <Database size={13} /> Open setup
                  </Link>
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-steel-500 text-[11px] font-bold text-white">
                  2
                </span>
                <span>
                  <b>Smart brief</b> — Aryx drafts these six answers from samples
                  (any model in Settings). Edit here anytime after.
                </span>
              </li>
            </ol>
            <p className="mt-3 text-[11px] text-subtle">
              Prefer not to invent the brief cold. After data lands, explore on{" "}
              <Link href="/data" className="underline">Data</Link>.
            </p>
          </div>

          <div className="mb-6 flex items-center gap-2">
            <FileText size={20} className="text-steel-600" />
            <div>
              <h1 className="font-display text-2xl font-bold text-navy-900">
                Brief
              </h1>
              <p className="text-[13px] text-subtle">
                Usually drafted after you load data in setup. Edit anytime —
                this steers extraction and Ask. Skip empty fields if unsure.
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
            <b>No data yet?</b>
            <p className="mt-1 text-[12px] text-subtle">
              Run setup first so Aryx can draft this brief from samples and propose
              multi-type graphs (e.g. Transaction + Merchant).
            </p>
            <Link
              href="/start"
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-navy-700"
            >
              <Database size={14} /> Open setup — load data
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
