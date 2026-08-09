"use client";

import { useMemo, useState } from "react";
import { FileText } from "lucide-react";
import { Header } from "@/components/brand/Header";
import { BriefBuilder } from "@/components/brief/BriefBuilder";
import { useWorkspace } from "@/lib/workspace";
import type { Brief } from "@/lib/types";

/** Revisit/edit surface for the workspace brief. New workspaces meet the
 *  same builder as step 1 of the Onboard wizard — this page is for coming
 *  back later. */
export default function BriefPage() {
  const { workspaceId, workspaces, setWorkspaceId, refresh } = useWorkspace();
  const [savedAt, setSavedAt] = useState(0);

  const initial = useMemo<Brief>(() => {
    const ws = workspaces.find((w) => w.id === workspaceId);
    return (ws?.brief ?? {}) as Brief;
    // savedAt forces a re-read after our own save round-trips through refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, workspaces, savedAt]);

  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <div className="mx-auto w-full max-w-3xl px-6 pb-8 pt-6">
          <div className="mb-6 flex items-center gap-2">
            <FileText size={20} className="text-steel-600" />
            <div>
              <h1 className="font-display text-2xl font-bold text-navy-900">Brief</h1>
              <p className="text-[13px] text-subtle">
                Six questions that ground every extraction. Skip any — Aryx
                just ingests more generically.
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
        </div>
      </main>
    </div>
  );
}
