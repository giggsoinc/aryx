"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Network, MessageCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { OntologyType } from "@/lib/types";
import { StepShell } from "./StepShell";

interface Props {
  workspaceId: number;
}

/** Screen 6 — what Aryx learned. Counts + two clear next-steps. */
export function Done({ workspaceId }: Props) {
  const [types, setTypes] = useState<OntologyType[]>([]);
  const [entityCount, setEntityCount] = useState(0);
  const [relCount, setRelCount] = useState(0);

  useEffect(() => {
    api.getOntology(workspaceId).then((d) => {
      setTypes(d.types || []);
      setEntityCount(d.entity_count || 0);
      setRelCount((d.relationships || []).length);
    }).catch(() => setTypes([]));
  }, [workspaceId]);

  return (
    <StepShell progress={100}>
      <h1 className="max-w-2xl text-center font-display text-[2rem] leading-tight text-navy-900">
        Here's what I learned:
      </h1>

      <div className="mt-8 flex max-w-3xl flex-wrap justify-center gap-3">
        {types.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-navy-200 bg-white px-6 py-5 text-center text-[13px] text-subtle">
            No records read yet — give it a moment, or hit refresh.
          </div>
        ) : (
          types.slice(0, 8).map((t) => (
            <div
              key={t.name}
              className="rounded-xl border-[1.5px] border-navy-100 bg-white px-5 py-3.5 text-center shadow-soft"
            >
              <div className="text-[14px] font-semibold text-navy-900">
                {t.name}
              </div>
              <div className="mt-1 font-mono text-[11px] text-subtle">
                {t.instance_count ?? 0} records
              </div>
            </div>
          ))
        )}
      </div>

      <div className="mt-5 text-[13px] text-subtle">
        <span className="font-semibold text-navy-700">
          {entityCount.toLocaleString()}
        </span>{" "}
        records · {" "}
        <span className="font-semibold text-navy-700">
          {relCount.toLocaleString()}
        </span>{" "}
        connections.
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          className="focus-ring inline-flex items-center gap-2 rounded-xl bg-navy-800 px-6 py-3 text-[15px] font-semibold text-white hover:bg-navy-700"
        >
          <MessageCircle size={15} /> Ask Aryx a question{" "}
          <ArrowRight size={15} />
        </Link>
        <Link
          href="/model"
          className="focus-ring inline-flex items-center gap-2 rounded-xl border border-navy-100 bg-white px-5 py-3 text-[14px] font-medium text-navy-700 hover:bg-navy-50"
        >
          <Network size={15} /> See the map
        </Link>
      </div>
    </StepShell>
  );
}
