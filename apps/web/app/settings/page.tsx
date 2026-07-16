"use client";

import { Header } from "@/components/brand/Header";
import { LlmSettings } from "@/components/settings/LlmSettings";
import { useWorkspace } from "@/lib/workspace";

/** Product settings — model provider (replaces legacy Streamlit Settings). */
export default function SettingsPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 bg-canvas">
        <LlmSettings />
      </main>
    </div>
  );
}
