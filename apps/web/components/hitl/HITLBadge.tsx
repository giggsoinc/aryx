"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageSquareWarning } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { HITLDrawer } from "./HITLDrawer";

const POLL_MS = 15_000;

/** Bell-style nav button — count of pending questions, opens HITLDrawer. */
export function HITLBadge() {
  const { workspaceId } = useWorkspace();
  const [pending, setPending] = useState(0);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const stats = await api.getIngestQuestionStats(workspaceId);
      setPending(Number(stats.pending) || 0);
    } catch {
      setPending(0);
    }
  }, [workspaceId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={`${pending} pending question${pending === 1 ? "" : "s"}`}
        className="focus-ring relative inline-flex size-9 items-center justify-center rounded-lg text-navy-600 transition-colors hover:bg-navy-50 hover:text-navy-900"
      >
        <MessageSquareWarning size={16} />
        {pending > 0 && (
          <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white shadow-sm">
            {pending > 99 ? "99+" : pending}
          </span>
        )}
      </button>
      <HITLDrawer
        open={open}
        workspaceId={workspaceId}
        onClose={() => setOpen(false)}
        onAnswered={refresh}
      />
    </>
  );
}
