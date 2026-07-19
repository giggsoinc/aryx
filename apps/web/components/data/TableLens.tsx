"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { typeColor } from "@/lib/typeColor";
import type {
  DataEntity, DataEntityGroup, DataEntitiesGrouped, DataTypeCount,
} from "@/lib/types";

const PAGE = 50;
const MAX_COLS = 6;

type Sort = { col: string; dir: "asc" | "desc" };

/** Records grid per type (sortable) + click-row provenance drawer. */
export function TableLens({ types }: { types: DataTypeCount[] }) {
  const { workspaceId } = useWorkspace();
  const [active, setActive] = useState(types[0]?.name ?? "");
  const [items, setItems] = useState<DataEntity[]>([]);
  const [total, setTotal] = useState(0);
  // Grouped mode (hub/spoke, e.g. child rows under their parent key). null = flat.
  const [groups, setGroups] = useState<DataEntityGroup[] | null>(null);
  const [groupAttr, setGroupAttr] = useState("");
  const [labelAttr, setLabelAttr] = useState<string | null>(null);
  const [totalGroups, setTotalGroups] = useState(0);
  const [busy, setBusy] = useState(false);
  const [sort, setSort] = useState<Sort | null>(null);
  const [selected, setSelected] = useState<DataEntity | null>(null);

  const apply = (d: Awaited<ReturnType<typeof api.dataEntities>>, append: boolean) => {
    if ("grouped" in d && d.grouped) {
      const g = d as DataEntitiesGrouped;
      setGroups((prev) => append && prev ? [...prev, ...g.groups] : g.groups);
      setGroupAttr(g.group_attr); setLabelAttr(g.label_attr);
      setTotalGroups(g.total_groups);
    } else {
      const p = d as { items?: DataEntity[]; total?: number };
      setGroups(null);
      setItems((prev) => append ? [...prev, ...(p.items || [])] : (p.items || []));
      setTotal(p.total || 0);
    }
  };

  useEffect(() => {
    if (!active) return;
    let live = true;
    setBusy(true); setItems([]); setGroups(null); setSelected(null); setSort(null);
    api.dataEntities(workspaceId, active, PAGE, 0, true)
      .then((d) => { if (live && !("error" in d && d.error)) apply(d, false); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [active, workspaceId]);

  const loadMore = async () => {
    setBusy(true);
    try {
      const offset = groups ? groups.length : items.length;
      const d = await api.dataEntities(workspaceId, active, PAGE, offset, true);
      if (!("error" in d && d.error)) apply(d, true);
    } finally { setBusy(false); }
  };

  const allItems = useMemo(
    () => groups ? groups.flatMap((g) => g.items) : items,
    [groups, items]);

  const cols = useMemo(() => {
    const freq = new Map<string, number>();
    for (const it of allItems)
      for (const [k, v] of Object.entries(it.attributes || {})) {
        if (k === "name") continue;
        if (v == null || v === "" || typeof v === "object") continue;
        freq.set(k, (freq.get(k) || 0) + 1);
      }
    return [...freq.entries()].sort((a, b) => b[1] - a[1])
      .slice(0, MAX_COLS).map((e) => e[0]);
  }, [allItems]);

  const sortItems = (list: DataEntity[]) => {
    if (!sort) return list;
    const val = (e: DataEntity) =>
      sort.col === "__name" ? e.name
        : sort.col === "__src" ? e.sources.length
        : (e.attributes?.[sort.col] ?? "");
    return [...list].sort((a, b) => {
      const x = val(a), y = val(b);
      const c = typeof x === "number" && typeof y === "number"
        ? x - y : String(x).localeCompare(String(y));
      return sort.dir === "asc" ? c : -c;
    });
  };

  const toggleSort = (col: string) =>
    setSort((s) => s?.col === col
      ? { col, dir: s.dir === "asc" ? "desc" : "asc" }
      : { col, dir: "asc" });

  const row = (e: DataEntity) => (
    <tr key={e.id} onClick={() => setSelected(e)}
      className={"cursor-pointer border-t border-navy-50 hover:bg-navy-50/40 " +
        (selected?.id === e.id ? "bg-navy-50" : "")}>
      <td className="px-3 py-2 font-medium text-navy-900">{e.name}</td>
      {cols.map((c) => (
        <td key={c} className="max-w-[200px] truncate px-3 py-2 text-navy-700">
          {fmt(e.attributes?.[c])}
        </td>
      ))}
      <td className="px-3 py-2">
        <span className="rounded-full bg-navy-50 px-2 py-0.5 text-[10.5px] font-semibold text-navy-600">
          {e.sources.length}
        </span>
      </td>
    </tr>
  );
  const span = cols.length + 2;

  return (
    <div className="grid gap-4 md:grid-cols-[170px_1fr]">
      <div className="h-fit overflow-hidden rounded-2xl border border-navy-100 bg-white">
        {types.map((t, i) => (
          <button key={t.name} type="button" onClick={() => setActive(t.name)}
            className={"flex w-full items-center gap-2 border-t border-navy-50 px-3 py-2.5 text-left text-[12.5px] first:border-t-0 " +
              (active === t.name ? "bg-navy-50 font-semibold text-navy-900"
                                 : "font-medium text-navy-700 hover:bg-navy-50/50")}>
            <span className="size-2 rounded-sm" style={{ background: typeColor(i) }} />
            {t.name}
            <span className="ml-auto text-[10.5px] text-subtle">{t.count}</span>
          </button>
        ))}
      </div>

      <div>
        <div className="overflow-x-auto rounded-2xl border border-navy-100 bg-white">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="bg-navy-50 text-[11px] uppercase tracking-[0.03em] text-navy-700">
                <Th label={groups ? (labelAttr || "Entity") : "Entity"}
                  onClick={() => toggleSort("__name")} sort={sort} col="__name" />
                {cols.map((c) => (
                  <Th key={c} label={c} onClick={() => toggleSort(c)} sort={sort} col={c} />
                ))}
                <Th label="Sources" onClick={() => toggleSort("__src")} sort={sort} col="__src" />
              </tr>
            </thead>
            <tbody>
              {groups ? groups.map((grp) => (
                <Fragment key={grp.key}>
                  <tr className="border-t border-navy-100 bg-steel-50/60">
                    <td colSpan={span} className="px-3 py-1.5 text-[11.5px] font-semibold text-navy-800">
                      <span className="text-subtle">{groupAttr}:</span> {grp.key}
                      <span className="ml-2 rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-navy-500">
                        {grp.count} line{grp.count === 1 ? "" : "s"}
                      </span>
                    </td>
                  </tr>
                  {sortItems(grp.items).map(row)}
                </Fragment>
              )) : sortItems(items).map(row)}
              {!busy && allItems.length === 0 && (
                <tr><td colSpan={span} className="px-3 py-8 text-center text-subtle">
                  No entities of this type.</td></tr>
              )}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-navy-100 px-3 py-2 text-[11px] text-subtle">
            <span>{busy ? "loading…"
              : groups
                ? `Showing ${groups.length} of ${totalGroups} ${groupAttr} group${totalGroups === 1 ? "" : "s"}`
                : `Showing ${items.length} of ${total}`}</span>
            {!busy && (groups ? groups.length < totalGroups : items.length < total) && (
              <button type="button" onClick={loadMore}
                className="font-medium text-steel-600 hover:underline">
                {groups
                  ? `Show ${Math.min(25, totalGroups - groups.length)} more group${totalGroups - groups.length === 1 ? "" : "s"}`
                  : `Show ${Math.min(PAGE, total - items.length)} more`}
              </button>
            )}
          </div>
        </div>

        {selected && <ProvenanceDrawer entity={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}

function Th({ label, onClick, sort, col }: {
  label: string; onClick: () => void; sort: Sort | null; col: string;
}) {
  const on = sort?.col === col;
  return (
    <th onClick={onClick}
      className="cursor-pointer select-none px-3 py-2 text-left font-semibold hover:text-navy-900">
      <span className="inline-flex items-center gap-1">
        {label}
        {on && (sort!.dir === "asc"
          ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
      </span>
    </th>
  );
}

function ProvenanceDrawer({ entity, onClose }: { entity: DataEntity; onClose: () => void }) {
  const attrs = Object.entries(entity.attributes || {})
    .filter(([, v]) => v !== null && v !== "" && typeof v !== "object");
  return (
    <div className="mt-3 rounded-2xl border border-steel-400/50 bg-gradient-to-b from-white to-[#FCFDFF] p-4">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-display text-[1.05rem] text-navy-900">{entity.name}</h4>
          <div className="mt-0.5 text-[11px] text-subtle">
            {entity.type} · id {entity.id} · {entity.sources.length} source record(s)
          </div>
        </div>
        <button type="button" onClick={onClose}
          className="rounded-md p-1 text-navy-400 hover:bg-navy-50"><X size={15} /></button>
      </div>

      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11.5px] text-navy-700">
        {attrs.map(([k, v]) => (
          <span key={k}><span className="text-subtle">{k}:</span> {String(v)}</span>
        ))}
      </div>

      <div className="mt-3 border-t border-navy-100 pt-2.5">
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-subtle">Provenance</div>
        <div className="mt-2 space-y-1.5">
          {entity.sources.map((s, i) => (
            <div key={`${i}-${s.record_id}`}
              className="flex items-center gap-2.5 rounded-lg border border-navy-100 bg-white px-3 py-1.5 text-[11.5px]">
              <span className="flex size-4 items-center justify-center rounded bg-navy-800 text-[9px] font-bold text-white">{i + 1}</span>
              <span className="font-mono text-[11px] text-steel-600">
                {s.system}.{s.dataset}#{s.record_id}
              </span>
            </div>
          ))}
          {entity.sources.length === 0 && (
            <span className="text-[11px] italic text-subtle">no provenance recorded</span>
          )}
        </div>
      </div>
    </div>
  );
}

function fmt(v: unknown): string {
  if (v == null) return "—";
  const s = String(v);
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
}
