"use client";

import { useState } from "react";
import type { DocumentEntity } from "@/lib/types";
import { ExcerptPanel } from "@/components/planner/ExcerptPanel";

interface Props {
  workspaceId: number;
  entities: DocumentEntity[];
}

// Deliberately no charting library — a Tailwind tag cloud (font-size scaled
// by mention count) covers the "what are these documents about, at a
// glance" acceptance criterion without adding a new dependency (no entry in
// manifest.stack.libraries yet, so anything new would first need a
// CVE-check/approval pass). A physics-packed layout is a later polish, not
// a v1 requirement.
const SIZE_STEPS = [
  "text-xs", "text-sm", "text-base", "text-lg", "text-xl", "text-2xl", "text-3xl",
];

function sizeClassFor(count: number, maxCount: number): string {
  if (maxCount <= 0) return SIZE_STEPS[0];
  const ratio = count / maxCount;
  const idx = Math.min(SIZE_STEPS.length - 1, Math.round(ratio * (SIZE_STEPS.length - 1)));
  return SIZE_STEPS[idx];
}

/** Tag cloud with click-to-reveal excerpts. Owns only which term is
 *  selected — the actual fetch/loading state lives in `ExcerptPanel`
 *  (mounted only for the selected term), so no excerpt text is ever
 *  fetched until a user clicks, and only for that one entity. */
export function WordCloudChart({ workspaceId, entities }: Props) {
  const [selected, setSelected] = useState<DocumentEntity | null>(null);
  const maxCount = entities.reduce((m, e) => Math.max(m, e.count), 0);
  return (
    <div className="py-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
        {entities.map((e) => {
          const isSelected = selected?.ontology_type === e.ontology_type && selected?.name === e.name;
          return (
            <button
              key={`${e.ontology_type}:${e.name}`}
              type="button"
              title={`${e.ontology_type} — mentioned ${e.count}× — click for sample quotes`}
              onClick={() => setSelected(isSelected ? null : e)}
              className={`${sizeClassFor(e.count, maxCount)} focus-ring cursor-pointer rounded font-medium underline decoration-dotted decoration-navy-300 underline-offset-4 transition-colors ${
                isSelected ? "text-steel-700 decoration-steel-500" : "text-navy-700 hover:text-steel-600 hover:decoration-steel-400"
              }`}
            >
              {e.name}
            </button>
          );
        })}
      </div>
      {selected && (
        <ExcerptPanel
          workspaceId={workspaceId}
          ontologyType={selected.ontology_type}
          name={selected.name}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
