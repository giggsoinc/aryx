"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { OntologyType } from "@/lib/types";

interface Props {
  workspaceId: number;
}

/** Compact banner — what's actually in this workspace, plus a hint that
 *  questions naming a specific type or entity work best with this dataset. */
export function WorkspacePeek({ workspaceId }: Props) {
  const [types, setTypes] = useState<OntologyType[]>([]);

  useEffect(() => {
    api.getOntology(workspaceId).then((d) => setTypes(d.types || []))
      .catch(() => setTypes([]));
  }, [workspaceId]);

  if (types.length === 0) return null;

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
