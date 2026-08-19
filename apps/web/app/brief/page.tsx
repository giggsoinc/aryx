"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Database, Eye, FileText, Pencil } from "lucide-react";
import { Header } from "@/components/brand/Header";
import { BriefBuilder } from "@/components/brief/BriefBuilder";
import { UnderstandingPanel } from "@/components/understanding/UnderstandingPanel";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useWorkspace } from "@/lib/workspace";
import type { Brief, WorkspaceUnderstanding } from "@/lib/types";

type Tab = "brief" | "understanding";

/**
 * Brief surface — two tabs, one authoritative.
 *
 * "Your brief" is customer-authored and editable; it is captured before
 * upload and is what ingestion and the dashboard are built against.
 * "What we understood" is Aryx's reading of the data after ingest: an info
 * view only, never editable, so the two can never silently swap places.
 */
export default function BriefPage() {
  const { workspaceId, workspaces, setWorkspaceId, refresh } = useWorkspace();
  const [tab, setTab] = useState<Tab>("brief");
  const [savedAt, setSavedAt] = useState(0);
  const [understanding, setUnderstanding] =
    useState<WorkspaceUnderstanding | null>(null);

  const initial = useMemo<Brief>(() => {
    const ws = workspaces.find((w) => w.id === workspaceId);
    return (ws?.brief ?? {}) as Brief;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, workspaces, savedAt]);

  const loadUnderstanding = useCallback(async () => {
    try {
      setUnderstanding(await api.getUnderstanding(workspaceId));
    } catch {
      setUnderstanding(null);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadUnderstanding();
  }, [loadUnderstanding, savedAt]);

  const du = understanding?.data_understanding ?? {};
  const derived = understanding?.brief_source === "derived";
  const hasReading = Boolean(du.brief || du.summary);

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-3xl px-6 pb-8 pt-6">
          <div className="mb-6 rounded-xl border border-navy-100 bg-white p-4 shadow-soft">
            <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-navy-500">
              Getting started · brief first
            </div>
            <ol className="mt-3 space-y-2 text-[13px] text-navy-800">
              <li className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-navy-800 text-[11px] font-bold text-white">
                  1
                </span>
                <span>
                  <b>Write the brief</b> — one sentence or a document is enough;
                  Aryx drafts the rest and you correct it. This is what
                  ingestion and your dashboard are built against.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-steel-500 text-[11px] font-bold text-white">
                  2
                </span>
                <span>
                  <b>Load your data</b> — Aryx reads it through this brief.{" "}
                  <Link
                    href="/start"
                    className="inline-flex items-center gap-1 font-semibold text-steel-600 underline hover:text-navy-800"
                  >
                    <Database size={13} /> Open setup
                  </Link>
                </span>
              </li>
            </ol>
          </div>

          {derived && (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
              <b>This brief was inferred from your data</b>, not written by you
              — the brief step was skipped. Editing it here makes it yours.
            </div>
          )}

          <div className="mb-4 flex items-center gap-2">
            <FileText size={20} className="text-steel-600" />
            <div>
              <h1 className="font-display text-2xl font-bold text-navy-900">
                Brief
              </h1>
              <p className="text-[13px] text-subtle">
                Captured before upload. Steers extraction, Ask, and the
                dashboard. Skip fields you&apos;re unsure of.
              </p>
            </div>
          </div>

          <div
            role="tablist"
            aria-label="Brief views"
            className="mb-5 inline-flex rounded-xl border border-navy-100 bg-white p-1 shadow-soft"
          >
            <TabButton
              active={tab === "brief"}
              onClick={() => setTab("brief")}
              icon={<Pencil size={13} />}
              label="Your brief"
            />
            <TabButton
              active={tab === "understanding"}
              onClick={() => setTab("understanding")}
              icon={<Eye size={13} />}
              label="What we understood"
            />
          </div>

          {tab === "brief" ? (
            <BriefBuilder
              workspaceId={workspaceId}
              initial={initial}
              submitLabel="Save Brief"
              onSubmitted={async () => {
                await refresh();
                setSavedAt(Date.now());
              }}
            />
          ) : hasReading ? (
            <>
              {du.summary && (
                <p className="mb-3 rounded-xl border border-navy-100 bg-white p-4 text-[13px] text-navy-800 shadow-soft">
                  {du.summary}
                </p>
              )}
              <UnderstandingPanel
                understood={(du.brief ?? {}) as Brief}
                divergences={du.divergences ?? []}
                gaps={du.gaps ?? []}
                fallback={du.fallback}
                promoted={du.promoted_to_brief}
              />
              <p className="mt-3 text-[11px] text-subtle">
                {du.source_files?.length
                  ? `Read from: ${du.source_files.join(", ")}. `
                  : ""}
                {du.generated_at
                  ? `Generated ${new Date(du.generated_at).toLocaleString()}.`
                  : ""}
              </p>
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-steel-400/50 bg-white/80 px-4 py-6 text-center">
              <p className="text-[13px] text-navy-800">
                <b>No data read yet.</b>
              </p>
              <p className="mt-1 text-[12px] text-subtle">
                Once you load data, Aryx&apos;s reading of it appears here —
                read-only, alongside your brief.
              </p>
              <Link
                href="/start"
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-navy-700"
              >
                <Database size={14} /> Open setup — load data
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "focus-ring inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-[12px] font-semibold transition-colors",
        active ? "bg-navy-800 text-white" : "text-navy-600 hover:bg-navy-50",
      )}
    >
      {icon} {label}
    </button>
  );
}
