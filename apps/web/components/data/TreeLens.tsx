"use client";

import { useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { typeColor } from "@/lib/typeColor";
import type { DataEntity, DataTypeCount } from "@/lib/types";

const PAGE = 25;

/** Types → entities → attributes + the source records each traces back to. */
export function TreeLens({ types }: { types: DataTypeCount[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-navy-100 bg-white">
      {types.map((t, i) => (
        <TypeRow key={t.name} type={t} color={typeColor(i)} />
      ))}
      {types.length === 0 && (
        <div className="px-5 py-8 text-center text-[13px] text-subtle">
          No entities yet — onboard a source to populate this workspace.
        </div>
      )}
    </div>
  );
}

function TypeRow({ type, color }: { type: DataTypeCount; color: string }) {
  const { workspaceId } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<DataEntity[]>([]);
  const [loaded, setLoaded] = useState(0);
  const [busy, setBusy] = useState(false);

  const loadMore = async () => {
    setBusy(true);
    try {
      const page = await api.dataEntities(workspaceId, type.name, PAGE, loaded);
      setItems((prev) => [...prev, ...(page.items || [])]);
      setLoaded((n) => n + (page.items?.length || 0));
    } finally {
      setBusy(false);
    }
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && items.length === 0) loadMore();
  };

  return (
    <div className="border-t border-navy-50 first:border-t-0">
      <button type="button" onClick={toggle}
        className="flex w-full items-center gap-2.5 px-4 py-3 text-left hover:bg-navy-50/40">
        <ChevronRight size={13} className={"text-navy-300 transition-transform " +
          (open ? "rotate-90" : "")} />
        <span className="size-2.5 rounded-sm" style={{ background: color }} />
        <span className="text-[13.5px] font-semibold text-navy-900">{type.name}</span>
        <span className="ml-auto rounded-full bg-navy-50 px-2.5 py-0.5 text-[11px] font-semibold text-subtle">
          {type.count}
        </span>
      </button>

      {open && (
        <div className="pb-1">
          {items.map((e) => <EntityRow key={e.id} entity={e} />)}
          {busy && (
            <div className="flex items-center gap-2 px-12 py-2 text-[12px] text-subtle">
              <Loader2 size={13} className="animate-spin" /> loading…
            </div>
          )}
          {!busy && loaded < type.count && (
            <button type="button" onClick={loadMore}
              className="px-12 py-2 text-[12px] font-medium text-steel-600 hover:underline">
              Show {Math.min(PAGE, type.count - loaded)} more of {type.count}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function EntityRow({ entity }: { entity: DataEntity }) {
  const [open, setOpen] = useState(false);
  const attrs = Object.entries(entity.attributes || {})
    .filter(([, v]) => v !== null && v !== "" && typeof v !== "object");
  return (
    <div>
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 bg-[#FCFDFF] py-2 pl-11 pr-4 text-left hover:bg-navy-50/40">
        <ChevronRight size={12} className={"text-navy-300 transition-transform " +
          (open ? "rotate-90" : "")} />
        <span className="text-[12.5px] font-medium text-navy-800">{entity.name}</span>
        <span className="ml-auto font-mono text-[10.5px] text-navy-300">id {entity.id}</span>
      </button>
      {open && (
        <div className="space-y-2 bg-[#FBFCFE] py-2.5 pl-[4.5rem] pr-5">
          {attrs.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-navy-700">
              {attrs.map(([k, v]) => (
                <span key={k}>
                  <span className="text-subtle">{k}:</span> {String(v)}
                </span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {entity.sources.map((s, i) => (
              <span key={`${i}-${s.record_id}`}
                className="rounded-md border border-navy-100 bg-white px-2 py-0.5 font-mono text-[10.5px] text-steel-600">
                {s.system}.{s.dataset}#{s.record_id}
              </span>
            ))}
            {entity.sources.length === 0 && (
              <span className="text-[11px] italic text-subtle">no provenance recorded</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
