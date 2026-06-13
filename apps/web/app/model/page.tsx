"use client";

import dynamic from "next/dynamic";
import { Header } from "@/components/brand/Header";
import { useWorkspace } from "@/lib/workspace";

// React Flow touches `window` during import; keep it client-only.
const Canvas = dynamic(
  () => import("@/components/model/Canvas").then((m) => m.Canvas),
  { ssr: false },
);

export default function ModelPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <Canvas />
    </div>
  );
}
