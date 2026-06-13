import dagre from "dagre";
import type { Edge, Node } from "@xyflow/react";

const NODE_W = 240;
const NODE_H = 120;

/**
 * Auto-layout nodes + edges with dagre. Stable: same input → same output.
 * Direction LR (left-right) reads like a schema diagram; switch to TB for
 * inheritance views.
 */
export function autoLayout(
  nodes: Node[],
  edges: Edge[],
  direction: "LR" | "TB" = "LR",
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100 });
  for (const n of nodes) g.setNode(n.id, { width: NODE_W, height: NODE_H });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return {
    nodes: nodes.map((n) => {
      const p = g.node(n.id);
      return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
    }),
    edges,
  };
}
