"use client";

import { Header } from "@/components/brand/Header";
import { IntentForm } from "@/components/intent/IntentForm";
import { DatasetsPanel } from "@/components/dataset/DatasetsPanel";
import { GraphIntakePanel } from "@/components/graph/GraphIntakePanel";
import { WorkspacePlanningContextPanel } from "@/components/planning/WorkspacePlanningContextPanel";
import { DashboardSpecPanel } from "@/components/planner/DashboardSpecPanel";
import { ExecutionPlanPanel } from "@/components/planner/ExecutionPlanPanel";
import { ExecutionRunPanel } from "@/components/planner/ExecutionRunPanel";
import { useWorkspace } from "@/lib/workspace";

export default function DashboardPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <main className="flex-1 space-y-2 py-2">
        {/* C01 — User Intent Capture */}
        <IntentForm workspaceId={workspaceId} />
        {/* C02/C03/C04 — Datasets, profiles, semantic mapping (read-only) */}
        <DatasetsPanel workspaceId={workspaceId} />
        {/* C05/C06 — Knowledge Graph Intake, Validation & Profiling */}
        <GraphIntakePanel workspaceId={workspaceId} />
        {/* C07 (workspace scope) — merged planning context across all datasets */}
        <WorkspacePlanningContextPanel workspaceId={workspaceId} />
        {/* C08 — Andie Jr Planning Orchestrator (on-demand; calls a real LLM) */}
        <DashboardSpecPanel workspaceId={workspaceId} />
        {/* C11 — Execution Compiler (read-only; compiled automatically after C08/C09/C10) */}
        <ExecutionPlanPanel workspaceId={workspaceId} />
        {/* C12 — Deterministic Analysis Execution (on-demand; press Run) */}
        <ExecutionRunPanel workspaceId={workspaceId} />
      </main>
    </div>
  );
}
