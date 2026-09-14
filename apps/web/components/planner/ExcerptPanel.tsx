"use client";

import { useEffect, useState } from "react";
import { Loader2, Quote, X } from "lucide-react";
import { api } from "@/lib/api";

interface Props {
  workspaceId: number;
  ontologyType: string;
  name: string;
  onClose: () => void;
}

/** On-demand excerpt reveal for one entity — fetches only when mounted
 *  (i.e. only when a user actually clicks a term), never as part of the
 *  eager word-cloud poll. Self-contained: owns its own fetch/loading state
 *  so WordCloudChart just mounts/unmounts it, no state lifted to
 *  DashboardRenderer. */
export function ExcerptPanel({ workspaceId, ontologyType, name, onClose }: Props) {
  const [excerpts, setExcerpts] = useState<string[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    setExcerpts(null);
    setError(false);
    api.getEntityExcerpts(workspaceId, ontologyType, name)
      .then((r) => { if (alive) setExcerpts(r.excerpts); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [workspaceId, ontologyType, name]);

  return (
    <div className="mt-3 rounded-lg border border-navy-100 bg-navy-50/30 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase text-navy-500">
          <Quote size={12} /> {name}
          {excerpts === null && !error && <Loader2 size={12} className="animate-spin" />}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="focus-ring rounded p-0.5 text-navy-400 hover:bg-navy-100 hover:text-navy-700"
          aria-label={`Close excerpts for ${name}`}
        >
          <X size={14} />
        </button>
      </div>
      {error && (
        <p className="mt-2 text-xs text-rose-600">Couldn&apos;t load excerpts — try again.</p>
      )}
      {excerpts !== null && excerpts.length === 0 && (
        <p className="mt-2 text-xs text-navy-400">No excerpt text available for this entity.</p>
      )}
      {excerpts !== null && excerpts.length > 0 && (
        <ul className="mt-2 space-y-2">
          {excerpts.map((text, i) => (
            <li key={i} className="border-l-2 border-navy-200 pl-3 text-sm italic text-navy-700">
              &ldquo;{text}&rdquo;
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
