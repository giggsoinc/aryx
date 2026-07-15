"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Maximize2, Minimize2 } from "lucide-react";
import {
  ReactFlow, Background, Controls, MiniMap, MarkerType, Position,
  useNodesState, useEdgesState,
  type Node, type Edge, type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { typeColor } from "@/lib/typeColor";
import type { EntityGraphView } from "@/lib/types";

const NODE_W = 156;
const NODE_H = 42;

/** Dagre left-to-right layout — clean for small graphs. */
function dagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 44, ranksep: 160, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}

/** Cluster layout for large graphs: group each connected component into a
 *  hub-and-spoke cluster (the highest-degree node — e.g. a Company — is the
 *  hub, its neighbours fan out beside it), then pack the clusters into a
 *  wrapping grid. This turns a meaningless 5k-node column into readable
 *  "company + its people" groups you can scroll through. */
function clusterLayout(nodes: Node[], edges: Edge[]): Node[] {
  const HUB_GAP = 230, ROW = 52, PAD = 80, MAX_ROW = 5200, SPOKE_W = NODE_W;
  const adj = new Map<string, string[]>();
  const deg = new Map<string, number>();
  nodes.forEach((n) => { adj.set(n.id, []); deg.set(n.id, 0); });
  edges.forEach((e) => {
    if (adj.has(e.source) && adj.has(e.target)) {
      adj.get(e.source)!.push(e.target);
      adj.get(e.target)!.push(e.source);
      deg.set(e.source, deg.get(e.source)! + 1);
      deg.set(e.target, deg.get(e.target)! + 1);
    }
  });
  // Connected components via BFS.
  const seen = new Set<string>();
  const comps: string[][] = [];
  for (const n of nodes) {
    if (seen.has(n.id)) continue;
    const q = [n.id]; seen.add(n.id); const c: string[] = [];
    while (q.length) {
      const id = q.pop()!; c.push(id);
      for (const m of adj.get(id) || []) if (!seen.has(m)) { seen.add(m); q.push(m); }
    }
    comps.push(c);
  }
  const clusters = comps.filter((c) => c.length > 1);
  const singles = comps.filter((c) => c.length === 1).map((c) => c[0]);
  const pos = new Map<string, { x: number; y: number }>();

  let cx = 0, cy = 0, rowH = 0;
  for (const c of clusters) {
    const hub = c.reduce((a, b) => (deg.get(b)! > deg.get(a)! ? b : a));
    const spokes = c.filter((id) => id !== hub);
    const clusterH = Math.max(1, spokes.length) * ROW;
    const clusterW = NODE_W + HUB_GAP + SPOKE_W;
    if (cx > 0 && cx + clusterW > MAX_ROW) { cx = 0; cy += rowH + PAD; rowH = 0; }
    pos.set(hub, { x: cx, y: cy + clusterH / 2 - NODE_H / 2 });
    spokes.forEach((s, i) => pos.set(s, { x: cx + NODE_W + HUB_GAP, y: cy + i * ROW }));
    cx += clusterW + PAD;
    rowH = Math.max(rowH, clusterH);
  }
  // Unconnected entities: a compact grid below the clusters.
  if (singles.length) {
    cx = 0; cy += rowH + PAD * 1.5;
    const perRow = Math.max(1, Math.floor(MAX_ROW / (NODE_W + 28)));
    singles.forEach((id, i) => {
      pos.set(id, {
        x: (i % perRow) * (NODE_W + 28),
        y: cy + Math.floor(i / perRow) * (NODE_H + 16),
      });
    });
  }
  return nodes.map((n) => ({ ...n, position: pos.get(n.id) || { x: 0, y: 0 } }));
}

function laidOut(nodes: Node[], edges: Edge[]): Node[] {
  return nodes.length > 60 ? clusterLayout(nodes, edges) : dagreLayout(nodes, edges);
}

/** Entity graph — every entity a draggable node, edges carry the relationship.
 *  Pan, zoom, minimap-navigate, and expand to fullscreen. */
export function GraphLens() {
  const { workspaceId } = useWorkspace();
  const [g, setG] = useState<EntityGraphView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [full, setFull] = useState(false);

  useEffect(() => {
    let live = true;
    setG(null); setErr(null);
    api.dataGraphEntity(workspaceId)
      .then((d) => { if (live) (("error" in d && d.error) ? setErr(d.error!) : setG(d)); })
      .catch((e) => { if (live) setErr(e instanceof Error ? e.message : "failed"); });
    return () => { live = false; };
  }, [workspaceId]);

  // Escape exits fullscreen.
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFull(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);

  if (err) return <Box><span className="text-rose-600">{err}</span></Box>;
  if (!g) return <Box><Loader2 size={16} className="animate-spin" /> building map…</Box>;
  if (g.entity_count === 0) {
    return <Box>No entities yet — ingest a source from the Onboard tab.</Box>;
  }

  const shell = full
    ? "fixed inset-0 z-[60] flex flex-col bg-white p-4"
    : "rounded-2xl border border-navy-100 bg-white p-3";

  const types = Array.from(new Set(g.nodes.map((n) => n.type)));

  return (
    <div className={shell}>
      <div className="mb-2 flex items-center justify-between px-2 pt-1 text-[11px] text-subtle">
        <div className="flex items-center gap-3">
          <span>{g.entity_count} entities · {g.relationship_count} relationships</span>
          <span className="flex items-center gap-2">
            {types.map((t, i) => (
              <span key={t} className="flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: typeColor(i) }} />
                {t}
              </span>
            ))}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline">drag · scroll to zoom · minimap to navigate</span>
          <button
            onClick={() => setFull((v) => !v)}
            className="flex items-center gap-1 rounded-lg border border-navy-100 px-2 py-1 font-medium text-navy-700 transition-colors hover:bg-navy-50"
            title={full ? "Exit fullscreen (Esc)" : "Fullscreen"}
          >
            {full ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            {full ? "Exit" : "Fullscreen"}
          </button>
        </div>
      </div>
      <Flow g={g} full={full} />
    </div>
  );
}

function Flow({ g, full }: { g: EntityGraphView; full: boolean }) {
  const [rf, setRf] = useState<ReactFlowInstance | null>(null);

  const typeColorMap = useMemo(() => {
    const types = Array.from(new Set(g.nodes.map((n) => n.type)));
    return new Map(types.map((t, i) => [t, typeColor(i)]));
  }, [g]);

  const initial = useMemo(() => {
    const rfNodes: Node[] = g.nodes.map((n) => ({
      id: String(n.id),
      data: { label: n.name },
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        width: NODE_W, height: NODE_H,
        background: typeColorMap.get(n.type),
        color: "#fff", border: "none", borderRadius: 10,
        fontSize: 11.5, fontWeight: 600, padding: "0 8px",
        display: "flex", alignItems: "center", justifyContent: "center",
        textAlign: "center" as const, boxShadow: "0 1px 2px rgba(20,40,80,.16)",
      },
    }));
    // Labels are readable only on a small graph; on a big one 4k identical
    // labels are pure noise, so drop them and keep the edges as light strokes.
    const showLabels = g.edges.length <= 120;
    const rfEdges: Edge[] = g.edges.map((e, i) => ({
      id: `e${i}`,
      source: String(e.source),
      target: String(e.target),
      ...(showLabels ? {
        label: e.name,
        labelStyle: { fontSize: 9.5, fontFamily: "JetBrains Mono, monospace", fill: "#2D4B8A" },
        labelBgStyle: { fill: "#fff", stroke: "#E4EAF4" },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 8,
      } : {}),
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94A8CB" },
      style: { stroke: "#C2CFE3", strokeWidth: 1.4 },
    }));
    return { nodes: laidOut(rfNodes, rfEdges), edges: rfEdges };
  }, [g, typeColorMap]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);

  useEffect(() => {
    setNodes(initial.nodes);
    setEdges(initial.edges);
  }, [initial, setNodes, setEdges]);

  // Re-fit when the container resizes (fullscreen toggle) or data reloads.
  useEffect(() => {
    if (!rf) return;
    const t = setTimeout(() => rf.fitView({ padding: 0.15 }), 80);
    return () => clearTimeout(t);
  }, [rf, full, initial]);

  return (
    <div className={full ? "min-h-0 flex-1 rounded-xl bg-[#FAFBFD]" : "rounded-xl bg-[#FAFBFD]"}
         style={full ? undefined : { height: 520 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={setRf}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.05}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
      >
        <Background color="#E4EAF4" gap={20} />
        <Controls showInteractive={false} />
        <MiniMap
          pannable zoomable
          nodeColor={(n) => (n.style?.background as string) || "#94A8CB"}
          nodeStrokeWidth={0}
          maskColor="rgba(20,40,80,.06)"
          style={{ background: "#fff", border: "1px solid #E4EAF4", borderRadius: 8 }}
        />
      </ReactFlow>
    </div>
  );
}

function Box({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-2xl border border-navy-100 bg-white px-4 py-16 text-[13px] text-subtle">
      {children}
    </div>
  );
}
