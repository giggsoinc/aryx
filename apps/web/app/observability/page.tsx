"use client";

import { Header } from "@/components/brand/Header";
import { ObservabilityPanel } from "@/components/observability/ObservabilityPanel";
import { useWorkspace } from "@/lib/workspace";

export default function ObservabilityPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <ObservabilityPanel />
      </main>
    </div>
  );
}
