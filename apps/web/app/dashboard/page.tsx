"use client";

import { Header } from "@/components/brand/Header";
import { AskToVisualizePanel } from "@/components/planner/AskToVisualizePanel";
import { DashboardRenderer } from "@/components/planner/DashboardRenderer";
import { useWorkspace } from "@/lib/workspace";

export default function DashboardPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 space-y-2 py-2">
        {/* Ask-to-visualize (C08 extension) — one chart at a time, appended */}
        <AskToVisualizePanel workspaceId={workspaceId} />
        {/* C15 — Frontend Dashboard Renderer: the actual final interface */}
        <DashboardRenderer workspaceId={workspaceId} />
      </main>
    </div>
  );
}
