"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, GitMerge, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { AdjudicationPreview, AdjudicationRow, AdjudicationSide } from "@/lib/types";

// No auth/user session exists in this app yet — every decision is recorded
// under this fixed reviewer id until real identity is wired up.
const REVIEWER = "web-ui";

function SidePanel({ side }: { side: AdjudicationSide }): JSX.Element {
  const entries = Object.entries(side.attributes || {}).slice(0, 8);
  return (
    <div className="flex-1 rounded-lg border border-navy-100 bg-navy-50/50 p-2.5">
      <div className="text-[11.5px] font-bold text-navy-800">
        {side.name || `Record #${side.record_id}`}
      </div>
      <div className="text-[10px] text-subtle">
        {side.entity_id != null ? `entity #${side.entity_id}` : "not yet resolved"}
      </div>
      <dl className="mt-1.5 space-y-0.5">
        {entries.length === 0 && (
          <div className="text-[10px] text-subtle">No attributes.</div>
        )}
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-1 text-[11px]">
            <dt className="shrink-0 font-medium text-navy-600">{k}:</dt>
            <dd className="truncate text-navy-800">{String(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Merge review queue — fetch pending pairs, show readable context, approve/reject.
 *  Approval merges the two entities server-side and re-projects the graph. */
export function AdjudicationReview({ workspaceId }: { workspaceId: number }): JSX.Element {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<AdjudicationRow[]>([]);
  const [pending, setPending] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [previews, setPreviews] = useState<Record<number, AdjudicationPreview | "loading">>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshStats = useCallback(() => {
    api.adjudicationStats(workspaceId)
      .then((s) => setPending(s.pending))
      .catch(() => setPending(null));
  }, [workspaceId]);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.listAdjudications(workspaceId, "pending");
      setRows(page);
      page.forEach((row) => {
        setPreviews((prev) => ({ ...prev, [row.id]: "loading" }));
        api.adjudicationPreview(workspaceId, row.id)
          .then((p) => setPreviews((prev) => ({ ...prev, [row.id]: p })))
          .catch(() => setPreviews((prev) => {
            const next = { ...prev };
            delete next[row.id];
            return next;
          }));
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => { refreshStats(); }, [refreshStats]);
  useEffect(() => { if (open) void loadQueue(); }, [open, loadQueue]);

  const dropRows = (ids: number[]) => {
    const drop = new Set(ids);
    setRows((prev) => prev.filter((r) => !drop.has(r.id)));
    setPreviews((prev) => {
      const next = { ...prev };
      ids.forEach((rid) => delete next[rid]);
      return next;
    });
  };

  const decide = async (id: number, approve: boolean) => {
    setBusyId(id);
    try {
      const res = await api.decideAdjudication(workspaceId, id, approve, REVIEWER);
      // Deciding this pair can silently resolve OTHER still-visible cards
      // too (they already collapsed to the same two entities) — drop those
      // from the list as well, or they'd sit there stale and 404 on click.
      dropRows([id, ...(res.duplicates_closed || [])]);
      refreshStats();
      // Same signal CorrectionChat uses after its own merges — GraphLens
      // already listens for it and refetches, so the graph updates live
      // instead of needing a manual page reload.
      if (res.merged) window.dispatchEvent(new CustomEvent("aryx:corrected"));
    } catch (e) {
      const message = e instanceof Error ? e.message : "decide failed";
      if (message.startsWith("404")) {
        // Someone/something else already resolved this pair (e.g. closed
        // as a duplicate of another decision) — stale card, not a real
        // failure. Drop it quietly instead of alarming the user.
        dropRows([id]);
        refreshStats();
      } else {
        setError(message);
      }
    } finally {
      setBusyId(null);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="focus-ring fixed bottom-5 left-5 z-40 inline-flex items-center gap-2 rounded-full bg-navy-800 px-4 py-2.5 text-[12px] font-semibold text-white shadow-lg hover:bg-navy-700"
      >
        <GitMerge size={14} /> Review merges
        {pending != null && pending > 0 && (
          <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-[10px]">{pending}</span>
        )}
      </button>
    );
  }

  return (
    <aside className="fixed bottom-0 left-0 top-16 z-40 flex w-[460px] flex-col border-r border-navy-100 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-navy-100 bg-navy-50/60 px-4 py-2.5">
        <div>
          <div className="text-[12px] font-bold text-navy-800">Pending entity merges</div>
          <div className="text-[10px] text-subtle">Review each pair · approving merges them now</div>
        </div>
        <button onClick={() => setOpen(false)} className="focus-ring rounded p-0.5 text-subtle hover:bg-navy-100">
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {loading && (
          <div className="flex items-center gap-1.5 text-[12px] text-subtle">
            <Loader2 size={12} className="animate-spin" /> Loading…
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
            {error}
          </div>
        )}
        {!loading && rows.length === 0 && !error && (
          <p className="text-[12px] text-subtle">Nothing pending review.</p>
        )}
        {rows.map((row) => {
          const preview = previews[row.id];
          const busy = busyId === row.id;
          return (
            <div key={row.id} className="rounded-lg border border-navy-100 p-2.5">
              <div className="mb-1.5 flex items-center justify-between text-[10px] text-subtle">
                <span>score {row.score.toFixed(2)}</span>
                {row.llm_verdict != null && <span>llm {Number(row.llm_verdict).toFixed(2)}</span>}
              </div>
              {preview === "loading" || preview === undefined ? (
                <div className="flex items-center gap-1.5 text-[11px] text-subtle">
                  <Loader2 size={11} className="animate-spin" /> loading context…
                </div>
              ) : (
                <div className="flex gap-2">
                  <SidePanel side={preview.left} />
                  <SidePanel side={preview.right} />
                </div>
              )}
              {preview && typeof preview !== "string" && preview.llm_reason && (
                <div className="mt-1.5 text-[10.5px] italic text-subtle">{preview.llm_reason}</div>
              )}
              <div className="mt-2 flex gap-2">
                <button
                  type="button" disabled={busy}
                  onClick={() => void decide(row.id, true)}
                  className={cn(
                    "focus-ring inline-flex items-center gap-1 rounded-lg bg-navy-800 px-3 py-1 text-[11.5px] font-semibold text-white hover:bg-navy-700 disabled:opacity-50",
                  )}
                >
                  <Check size={11} /> Approve &amp; merge
                </button>
                <button
                  type="button" disabled={busy}
                  onClick={() => void decide(row.id, false)}
                  className="focus-ring rounded-lg border border-navy-100 bg-white px-3 py-1 text-[11.5px] font-medium text-navy-700 hover:bg-navy-50 disabled:opacity-50"
                >
                  Reject
                </button>
                {busy && <Loader2 size={13} className="animate-spin text-subtle" />}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
