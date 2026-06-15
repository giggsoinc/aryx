"use client";

import { Header } from "@/components/brand/Header";
import { AbLab } from "@/components/lab/AbLab";
import { useWorkspace } from "@/lib/workspace";

export default function LabPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1">
        <AbLab />
      </main>
    </div>
  );
}
