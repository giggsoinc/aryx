"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { OntologyType } from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** Compact banner — what's actually in this workspace.
 *  EMPTY state is loud: when there are zero records (regardless of
 *  whether any types are registered), surface a big "Start setup" CTA
 *  instead of pretending there's data to ask about. */
export function WorkspacePeek({ workspaceId }: Props) {
  const [types, setTypes] = useState<OntologyType[]>([]);
  const [entityCount, setEntityCount] = useState<number | null>(null);

  useEffect(() => {
    api.getOntology(workspaceId).then((d) => {
      setTypes(d.types || []);
      setEntityCount(d.entity_count || 0);
    }).catch(() => { setTypes([]); setEntityCount(null); });
  }, [workspaceId]);

  if (entityCount === null) return null;

  if (entityCount === 0) {
    return (
      <div className="mb-6 rounded-2xl border-[1.5px] border-dashed border-amber-300 bg-amber-50/60 px-5 py-5 text-center">
        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-amber-700">
          This workspace is empty
        </div>
        <div className="mt-1 text-[14px] text-navy-900">
          No records yet — there's nothing to ask about. Run the guided
          setup to bring in your data.
        </div>
        <Link
          href="/start"
          className="focus-ring mt-3 inline-flex items-center gap-2 rounded-xl bg-navy-800 px-4 py-2 text-[13px] font-semibold text-white hover:bg-navy-700"
        >
          <Sparkles size={14} /> Start guided setup
        </Link>
      </div>
    );
  }

  return (
    <div className="mb-6 rounded-2xl border border-navy-100 bg-white px-5 py-4 shadow-soft">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-subtle">
          In this workspace
        </div>
        <Link
          href="/model"
          className="text-[11px] font-medium text-steel-500 hover:text-steel-600"
        >
          See the map →
        </Link>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {types.map((t) => (
          <span
            key={t.name}
            className="inline-flex items-center gap-1.5 rounded-full border border-navy-100 bg-navy-50/40 px-3 py-1 text-[12px]"
          >
            <span className="font-semibold text-navy-900">{t.name}</span>
            <span className="font-mono text-[11px] text-subtle">
              {t.instance_count ?? 0}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
