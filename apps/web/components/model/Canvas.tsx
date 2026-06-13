"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow,
  ReactFlowProvider, useEdgesState, useNodesState,
  type Edge, type Node, type NodeMouseHandler, type OnConnect, addEdge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { autoLayout } from "@/lib/canvasLayout";
import type { OntologyDoc } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";
import {
  EntityTypeNode, type EntityTypeNodeData,
} from "./EntityTypeNode";
import { Inspector } from "./Inspector";
import { Toolbar } from "./Toolbar";
import { NewTypeDialog } from "./NewTypeDialog";

const nodeTypes = { entityType: EntityTypeNode };

function ontologyToGraph(doc: OntologyDoc): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = (doc.types || []).map((t) => ({
    id: t.name,
    type: "entityType",
    position: { x: 0, y: 0 },
    data: {
      label: t.name,
      attributes: t.attributes || [],
      status: t.status || "approved",
      instanceCount: t.instance_count,
      parent: t.parent_type ?? null,
    } satisfies EntityTypeNodeData,
  }));
  const known = new Set(nodes.map((n) => n.id));
  const edges: Edge[] = [];
  for (const t of doc.types || []) {
    if (t.parent_type && known.has(t.parent_type)) {
      edges.push({
        id: `subClassOf::${t.name}::${t.parent_type}`,
        source: t.parent_type,
        target: t.name,
        label: "subClassOf",
        animated: false,
        style: { stroke: "#94A8CB", strokeDasharray: "4 4" },
      });
    }
  }
  for (const r of doc.relationships || []) {
    if (!r.source_type || !r.target_type) continue;
    if (!known.has(r.source_type) || !known.has(r.target_type)) continue;
    edges.push({
      id: `rel::${r.source_type}::${r.name}::${r.target_type}`,
      source: r.source_type,
      target: r.target_type,
      label: r.name,
      style: { stroke: "#4068A8" },
    });
  }
  return { nodes, edges };
}

function CanvasInner() {
  const { workspaceId } = useWorkspace();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [doc, setDoc] = useState<OntologyDoc | null>(null);
  const [showNewType, setShowNewType] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.getOntology(workspaceId);
      setDoc(d);
      const { nodes: n, edges: e } = ontologyToGraph(d);
      const laid = autoLayout(n, e, "LR");
      setNodes(laid.nodes);
      setEdges(laid.edges);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, setNodes, setEdges]);

  useEffect(() => { load(); }, [load]);

  const onNodeClick: NodeMouseHandler = useCallback((_, n) => {
    setSelected(n.id);
  }, []);

  const onPaneClick = useCallback(() => setSelected(null), []);

  const onConnect: OnConnect = useCallback(
    (c) => {
      const name = window.prompt(
        "Relationship name (snake_case, e.g. opened_by)",
        "relates_to",
      );
      if (!name?.trim()) return;
      setEdges((es) => addEdge(
        {
          ...c,
          id: `draft::${c.source}::${name}::${c.target}::${Date.now()}`,
          label: name.trim(),
          style: { stroke: "#4068A8", strokeDasharray: "6 4" },
          data: { draft: true },
        },
        es,
      ));
    },
    [setEdges],
  );

  const relayout = useCallback(() => {
    const laid = autoLayout(nodes, edges, "LR");
    setNodes(laid.nodes);
    setEdges(laid.edges);
  }, [nodes, edges, setNodes, setEdges]);

  const selectedType = useMemo(
    () => doc?.types.find((t) => t.name === selected) || null,
    [doc, selected],
  );

  return (
    <div className="relative flex flex-1 overflow-hidden">
      <div className="relative flex-1">
        <Toolbar
          onRelayout={relayout}
          onRefresh={load}
          onNewType={() => setShowNewType(true)}
          typeCount={doc?.types.length || 0}
          relCount={doc?.relationships.length || 0}
          loading={loading}
        />
        {!loading && (doc?.types.length ?? 0) === 0 && (
          <EmptyState onCreate={() => setShowNewType(true)} />
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
          className="bg-canvas"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={24}
            size={1.2}
            color="#D5DDEC"
          />
          <Controls
            showInteractive={false}
            className="!rounded-xl !border !border-navy-100 !bg-white !shadow-soft"
          />
          <MiniMap
            pannable
            zoomable
            nodeColor="#1A2F55"
            maskColor="rgba(15,31,61,0.06)"
            className="!rounded-xl !border !border-navy-100 !bg-white !shadow-soft"
          />
        </ReactFlow>
      </div>
      <Inspector
        type={selectedType}
        workspaceId={workspaceId}
        onClose={() => setSelected(null)}
        onChanged={load}
      />
      <NewTypeDialog
        open={showNewType}
        workspaceId={workspaceId}
        onClose={() => setShowNewType(false)}
        onCreated={load}
      />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="pointer-events-none absolute inset-0 z-[5] flex items-center justify-center">
      <div className="pointer-events-auto max-w-md rounded-2xl border border-dashed border-navy-200 bg-white/70 px-8 py-10 text-center shadow-soft backdrop-blur">
        <h2 className="font-display text-[1.6rem] text-navy-900">
          No ontology yet.
        </h2>
        <p className="mt-2 text-[13px] text-subtle">
          Run an ingest, or start modelling by hand. Draw nodes for the
          entities in your domain, then drag between them to declare
          relationships.
        </p>
        <button
          onClick={onCreate}
          className="focus-ring mt-5 inline-flex items-center gap-2 rounded-lg bg-navy-800 px-4 py-2 text-[13px] font-semibold text-white hover:bg-navy-700"
        >
          + Create the first type
        </button>
      </div>
    </div>
  );
}

export function Canvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}
