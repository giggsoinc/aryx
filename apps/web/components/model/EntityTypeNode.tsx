"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Database, CircleAlert, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/cn";

export interface EntityTypeNodeData extends Record<string, unknown> {
  label: string;
  attributes: string[];
  status: "proposed" | "approved" | string;
  instanceCount?: number;
  parent?: string | null;
}

function NodeImpl({ data, selected }: NodeProps) {
  const d = data as EntityTypeNodeData;
  const isProposed = d.status === "proposed";
  return (
    <div
      className={cn(
        "min-w-[240px] max-w-[280px] rounded-xl border bg-white text-left shadow-soft transition-all",
        selected
          ? "border-steel-500 shadow-glow"
          : "border-navy-100 hover:border-navy-200",
        isProposed && "border-dashed",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-2 !border-white !bg-steel-500"
      />
      <div className="flex items-center justify-between border-b border-navy-100/70 px-4 py-2.5">
        <div className="flex items-center gap-2 truncate">
          <Database size={14} className="shrink-0 text-steel-500" />
          <span className="truncate text-[14px] font-semibold text-navy-800">
            {d.label}
          </span>
        </div>
        {isProposed ? (
          <span title="Proposed — needs approval"
                className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
            <CircleAlert size={10} /> proposed
          </span>
        ) : (
          <CheckCircle2 size={12} className="text-emerald-500" />
        )}
      </div>
      <div className="px-4 py-2.5">
        {d.attributes.length === 0 ? (
          <p className="text-[11px] italic text-subtle">no attributes</p>
        ) : (
          <ul className="space-y-0.5">
            {d.attributes.slice(0, 5).map((a) => (
              <li
                key={a}
                className="truncate font-mono text-[11px] text-navy-600"
              >
                · {a}
              </li>
            ))}
            {d.attributes.length > 5 && (
              <li className="text-[10px] text-subtle">
                + {d.attributes.length - 5} more
              </li>
            )}
          </ul>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-navy-100/70 bg-navy-50/40 px-4 py-1.5">
        <span className="text-[10px] uppercase tracking-wider text-subtle">
          {d.parent ? `↳ ${d.parent}` : "Root"}
        </span>
        <span className="text-[10px] font-medium text-navy-600">
          {d.instanceCount ?? 0} instances
        </span>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-2 !border-white !bg-steel-500"
      />
    </div>
  );
}

export const EntityTypeNode = memo(NodeImpl);
