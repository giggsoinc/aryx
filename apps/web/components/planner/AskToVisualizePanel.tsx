"use client";

import { useState } from "react";
import {
  Loader2, MessageSquarePlus, CheckCircle2, XCircle, AlertTriangle, X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import type { DeltaDraftResult } from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** Ask-to-visualize (C08 extension) — a customer types a chart request, sees
 *  a preview (grounded + structurally validated, nothing persisted yet),
 *  and confirms to have it appended to the existing dashboard. Confirm
 *  re-validates server-side regardless of what this preview showed (never
 *  trust a client-echoed draft) and chains execution + composition in one
 *  call — `DashboardRenderer` on the page already polls every 4s and picks
 *  up the result without this component needing to do anything else.
 *
 *  Rendered as a floating chat bubble + docked side panel (same pattern as
 *  JobsBadge's panel) rather than an inline card, so it doesn't compete
 *  with the dashboard itself for page real estate. */
export function AskToVisualizePanel({ workspaceId }: Props) {
  const datasetId = `workspace_${workspaceId}`;
  const [open, setOpen] = useState(false);
  const [requestText, setRequestText] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<DeltaDraftResult | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDraft = async () => {
    if (!requestText.trim()) return;
    setDrafting(true);
    setError(null);
    setConfirmed(false);
    try {
      setDraft(await api.draftDelta(workspaceId, datasetId, requestText.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDraft(null);
    } finally {
      setDrafting(false);
    }
  };

  const confirm = async () => {
    if (!draft?.items) return;
    setConfirming(true);
    setError(null);
    try {
      const result = await api.confirmDelta(workspaceId, datasetId, draft.items);
      if (result.status === "valid") {
        setConfirmed(true);
        setDraft(null);
        setRequestText("");
      } else {
        setError(`Rejected on confirm (${result.error_code ?? result.status}) — the request may have changed since drafting; try again.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirming(false);
    }
  };

  const discard = () => {
    setDraft(null);
    setError(null);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Ask for a chart"
        className="focus-ring fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-full bg-navy-900 px-4 py-3 text-sm font-medium text-white shadow-soft transition-colors hover:bg-navy-800"
      >
        <MessageSquarePlus size={18} />
        Ask for a chart
      </button>

      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ x: 420, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 420, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-16 z-30 flex h-[calc(100vh-4rem)] w-[420px] flex-col border-l border-navy-100 bg-white shadow-soft"
          >
            <header className="flex items-center justify-between border-b border-navy-100 px-5 py-3">
              <div className="flex items-center gap-2">
                <MessageSquarePlus size={16} className="text-navy-500" />
                <h2 className="font-display text-[1.05rem] text-navy-900">
                  Ask for a Chart
                </h2>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="focus-ring rounded-lg p-1 text-subtle hover:bg-navy-50"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-5 py-4">
              <p className="text-sm text-navy-500">
                Describe one chart you want added to the dashboard. Andie drafts
                it against what's already approved — never invents a column,
                KPI, or chart type — and shows a preview before anything is
                added.
              </p>

              <div className="mt-3 flex flex-col gap-2">
                <input
                  value={requestText}
                  onChange={(e) => setRequestText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !drafting) runDraft(); }}
                  placeholder="e.g. average deal size by product family as a box plot"
                  className="w-full rounded-lg border border-navy-200 px-3 py-2 text-sm text-navy-900 outline-none focus:border-navy-300"
                />
                <button onClick={runDraft} disabled={drafting || !requestText.trim()}
                        className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg bg-navy-900 px-4 py-2 text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-60">
                  {drafting && <Loader2 size={15} className="animate-spin" />}
                  {drafting ? "Drafting…" : "Draft chart"}
                </button>
              </div>

              {error && (
                <div className="mt-3 flex items-start gap-1.5 rounded-lg border border-red-200 bg-red-50/50 px-3 py-2 text-sm text-red-700">
                  <XCircle size={14} className="mt-0.5 shrink-0" /> {error}
                </div>
              )}

              {confirmed && (
                <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50/50 px-3 py-2 text-sm text-emerald-700">
                  <CheckCircle2 size={14} /> Added — the dashboard will refresh shortly.
                </div>
              )}

              {draft && <DraftPreview draft={draft} confirming={confirming} onConfirm={confirm} onDiscard={discard} />}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}

function DraftPreview({ draft, confirming, onConfirm, onDiscard }: {
  draft: DeltaDraftResult; confirming: boolean; onConfirm: () => void; onDiscard: () => void;
}) {
  if (draft.status === "controlled_error") {
    return (
      <div className="mt-3 flex items-start gap-1.5 rounded-lg border border-red-200 bg-red-50/50 px-3 py-2 text-sm text-red-700">
        <XCircle size={14} className="mt-0.5 shrink-0" />
        Could not draft a chart ({draft.error_code}): {draft.error_message}
      </div>
    );
  }

  const ok = draft.status === "valid" && draft.would_validate && !!draft.items?.new_visualization;
  return (
    <div className={`mt-3 rounded-lg border p-3 ${ok ? "border-sky-200 bg-sky-50/50" : "border-amber-200 bg-amber-50/50"}`}>
      <div className="flex items-center gap-1.5 text-sm font-medium text-navy-900">
        {ok ? <CheckCircle2 size={14} className="text-sky-600" /> : <AlertTriangle size={14} className="text-amber-600" />}
        {draft.preview_text}
      </div>

      {draft.validation_errors.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {draft.validation_errors.map((e, i) => (
            <li key={i} className="text-xs text-amber-800">— {e}</li>
          ))}
        </ul>
      )}
      {draft.items?.warnings.map((w, i) => (
        <div key={i} className="mt-1 text-xs text-navy-500">
          {w.code}{w.column ? ` · ${w.column}` : ""}{w.detail ? ` — ${w.detail}` : ""}
        </div>
      ))}

      <div className="mt-3 flex items-center gap-2">
        <button onClick={onConfirm} disabled={!ok || confirming}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-navy-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-navy-800 disabled:opacity-60">
          {confirming && <Loader2 size={13} className="animate-spin" />}
          {confirming ? "Adding…" : "Confirm — add to dashboard"}
        </button>
        <button onClick={onDiscard} disabled={confirming}
                className="focus-ring rounded-lg border border-navy-200 px-3 py-1.5 text-xs font-medium text-navy-600 hover:bg-navy-50 disabled:opacity-60">
          Discard
        </button>
      </div>
    </div>
  );
}
