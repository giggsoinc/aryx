"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { typeColor } from "@/lib/typeColor";
import type { GraphView } from "@/lib/types";

const W = 820;
const H = 460;
const CX = W / 2;
const CY = H / 2;
const RING = 165;

function radius(count: number): number {
  return Math.max(20, Math.min(46, 16 + Math.sqrt(count) * 1.7));
}

/** Type-level knowledge map: one node per type (sized by count), edges
 *  aggregated by relationship with counts. Legible at any scale. */
export function GraphLens() {
  const { workspaceId } = useWorkspace();
  const [g, setG] = useState<GraphView | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setG(null); setErr(null);
    api.dataGraph(workspaceId)
      .then((d) => { if (live) (("error" in d && d.error) ? setErr(d.error!) : setG(d)); })
      .catch((e) => { if (live) setErr(e instanceof Error ? e.message : "failed"); });
    return () => { live = false; };
  }, [workspaceId]);

  if (err) return <Box><span className="text-rose-600">{err}</span></Box>;
  if (!g) return <Box><Loader2 size={16} className="animate-spin" /> building map…</Box>;

  const nodes = g.type_nodes;
  const pos = new Map<string, { x: number; y: number; r: number; color: string }>();
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(1, nodes.length) - Math.PI / 2;
    pos.set(n.type, {
      x: CX + RING * Math.cos(a),
      y: CY + RING * Math.sin(a),
      r: radius(n.count),
      color: typeColor(i),
    });
  });

  return (
    <div className="rounded-2xl border border-navy-100 bg-white p-3">
      <div className="mb-1 flex items-center justify-between px-2 pt-1 text-[11px] text-subtle">
        <span>{g.entity_count} entities · {g.relationship_count} relationships</span>
        <span>node size = count · edge label = relationship (count)</span>
      </div>
      {g.relationship_count === 0 ? (
        <p className="px-2 py-6 text-center text-[12.5px] text-subtle">
          Entities exist but no relationships are defined yet — the map shows the
          types; connect them with foreign-key links to see the graph.
        </p>
      ) : null}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
                  markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="#94A8CB" />
          </marker>
        </defs>
        {g.type_edges.map((e, i) => {
          const s = pos.get(e.source); const t = pos.get(e.target);
          if (!s || !t) return null;
          const dx = t.x - s.x, dy = t.y - s.y;
          const len = Math.hypot(dx, dy) || 1;
          const ux = dx / len, uy = dy / len;
          const x1 = s.x + ux * s.r, y1 = s.y + uy * s.r;
          const x2 = t.x - ux * (t.r + 8), y2 = t.y - uy * (t.r + 8);
          const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
          const label = `${e.name} (${e.count})`;
          return (
            <g key={i}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#C2CFE3"
                    strokeWidth={1.6} markerEnd="url(#arrow)" />
              <g transform={`translate(${mx} ${my})`}>
                <rect x={-label.length * 3.1} y={-8} width={label.length * 6.2}
                      height={16} rx={8} fill="#fff" stroke="#E4EAF4" />
                <text textAnchor="middle" y={3.5} fontSize="9.5"
                      fontFamily="JetBrains Mono, monospace" fill="#2D4B8A">
                  {label}
                </text>
              </g>
            </g>
          );
        })}
        {nodes.map((n) => {
          const p = pos.get(n.type)!;
          return (
            <g key={n.type}>
              <circle cx={p.x} cy={p.y} r={p.r} fill={p.color} />
              <text x={p.x} y={p.y - 1} textAnchor="middle" fontSize="12"
                    fontWeight="600" fill="#fff">{n.type}</text>
              <text x={p.x} y={p.y + 12} textAnchor="middle" fontSize="10"
                    fill="#fff" opacity="0.9">{n.count}</text>
            </g>
          );
        })}
      </svg>
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
