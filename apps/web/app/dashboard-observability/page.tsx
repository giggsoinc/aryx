"use client";

import { Header } from "@/components/brand/Header";
import { IntentForm } from "@/components/intent/IntentForm";
import { DatasetsPanel } from "@/components/dataset/DatasetsPanel";
import { GraphIntakePanel } from "@/components/graph/GraphIntakePanel";
import { WorkspacePlanningContextPanel } from "@/components/planning/WorkspacePlanningContextPanel";
import { DashboardSpecPanel } from "@/components/planner/DashboardSpecPanel";
import { ExecutionPlanPanel } from "@/components/planner/ExecutionPlanPanel";
import { ExecutionRunPanel } from "@/components/planner/ExecutionRunPanel";
import { DashboardModelPanel } from "@/components/planner/DashboardModelPanel";
import { FoldableSection } from "@/components/planner/FoldableSection";
import { PipelineNav, type PipelineNavItem } from "@/components/planner/PipelineNav";
import { useWorkspace } from "@/lib/workspace";

const NAV_ITEMS: PipelineNavItem[] = [
  { id: "intent", label: "Intent Capture" },
  { id: "datasets", label: "Datasets" },
  { id: "graph-intake", label: "Graph Intake" },
  { id: "planning-context", label: "Planning Context" },
  { id: "dashboard-spec", label: "Dashboard Spec" },
  { id: "execution-plan", label: "Execution Plan" },
  { id: "execution-run", label: "Execution Run" },
  { id: "dashboard-model", label: "Dashboard Composition" },
];

export default function DashboardObservabilityPage() {
  const { workspaceId, setWorkspaceId } = useWorkspace();
  return (
    <div className="flex min-h-screen flex-col">
      <Header workspaceId={workspaceId} onWorkspaceChange={setWorkspaceId} />
      <div className="mx-auto flex w-full max-w-[88rem] flex-1 items-start gap-2 px-2">
        <PipelineNav items={NAV_ITEMS} />
        <main className="min-w-0 flex-1 space-y-2 py-2">
          {/* C01 — User Intent Capture */}
          <FoldableSection id="intent" title="Intent Capture" defaultOpen={false}>
            <IntentForm workspaceId={workspaceId} />
          </FoldableSection>
          {/* C02/C03/C04 — Datasets, profiles, semantic mapping (read-only) */}
          <FoldableSection id="datasets" title="Datasets" defaultOpen={false}>
            <DatasetsPanel workspaceId={workspaceId} />
          </FoldableSection>
          {/* C05/C06 — Knowledge Graph Intake, Validation & Profiling */}
          <FoldableSection id="graph-intake" title="Graph Intake" defaultOpen={false}>
            <GraphIntakePanel workspaceId={workspaceId} />
          </FoldableSection>
          {/* C07 (workspace scope) — merged planning context across all datasets */}
          <FoldableSection id="planning-context" title="Planning Context" defaultOpen={false}>
            <WorkspacePlanningContextPanel workspaceId={workspaceId} />
          </FoldableSection>
          {/* C08 — Aryx Insight Orchestrator (on-demand; calls a real LLM) */}
          <FoldableSection id="dashboard-spec" title="Dashboard Spec">
            <DashboardSpecPanel workspaceId={workspaceId} />
          </FoldableSection>
          {/* C11 — Execution Compiler (read-only; compiled automatically after C08/C09/C10) */}
          <FoldableSection id="execution-plan" title="Execution Plan">
            <ExecutionPlanPanel workspaceId={workspaceId} />
          </FoldableSection>
          {/* C12 — Deterministic Analysis Execution (on-demand; press Run) */}
          <FoldableSection id="execution-run" title="Execution Run">
            <ExecutionRunPanel workspaceId={workspaceId} />
          </FoldableSection>
          {/* C14 — Dashboard Composition (on-demand; gated on C13) */}
          <FoldableSection id="dashboard-model" title="Dashboard Composition">
            <DashboardModelPanel workspaceId={workspaceId} />
          </FoldableSection>
        </main>
      </div>
    </div>
  );
}
