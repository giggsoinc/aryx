"use client";

import { Header } from "@/components/brand/Header";
import { CorrectionChat } from "@/components/corrections/CorrectionChat";
import { DataExplorer } from "@/components/data/DataExplorer";
import { useWorkspace } from "@/lib/workspace";

export default function DataPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1">
        <DataExplorer />
      </main>
      <CorrectionChat workspaceId={workspaceId} scope="data" />
    </div>
  );
}
