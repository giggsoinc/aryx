"use client";

import { Layout, RefreshCw, Loader2, Plus } from "lucide-react";
import { cn } from "@/lib/cn";

interface ToolbarProps {
  onRelayout: () => void;
  onRefresh: () => void;
  onNewType: () => void;
  typeCount: number;
  relCount: number;
  loading?: boolean;
}

/** Floating top-left toolbar over the canvas. */
export function Toolbar({
  onRelayout, onRefresh, onNewType, typeCount, relCount, loading,
}: ToolbarProps) {
  return (
    <div className="pointer-events-none absolute left-6 top-6 z-10 flex items-center gap-3">
      <div className="pointer-events-auto inline-flex items-center gap-2 rounded-xl border border-navy-100 bg-white px-4 py-2 shadow-soft">
        <div className="text-[11px] uppercase tracking-wider text-subtle">
          Ontology
        </div>
        <div className="flex items-center gap-3 border-l border-navy-100/80 pl-3 text-[12px] font-medium text-navy-700">
          <span>{typeCount} types</span>
          <span className="text-navy-200">·</span>
          <span>{relCount} relationships</span>
        </div>
      </div>
      <div className="pointer-events-auto inline-flex items-center gap-1 rounded-xl border border-navy-100 bg-white p-1 shadow-soft">
        <button
          type="button"
          onClick={onNewType}
          title="Create a new entity type"
          className="focus-ring inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-2.5 py-1.5 text-[12px] font-semibold text-white hover:bg-navy-700"
        >
          <Plus size={13} /> New type
        </button>
        <span className="mx-0.5 h-5 w-px bg-navy-100" />
        <button
          type="button"
          onClick={onRelayout}
          title="Auto-layout"
          className={cn(
            "focus-ring inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-navy-700",
            "hover:bg-navy-50",
          )}
        >
          <Layout size={13} /> Auto-layout
        </button>
        <button
          type="button"
          onClick={onRefresh}
          title="Refresh from API"
          disabled={loading}
          className={cn(
            "focus-ring inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-navy-700 hover:bg-navy-50",
            loading && "opacity-50",
          )}
        >
          {loading ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RefreshCw size={13} />
          )}
          Refresh
        </button>
      </div>
    </div>
  );
}
