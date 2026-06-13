import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Citation as CitationT } from "@/lib/types";

interface Props {
  citations: CitationT[];
  className?: string;
}

/** Inline citation pills under an assistant message. */
export function Citations({ citations, className }: Props) {
  if (!citations.length) return null;
  return (
    <div className={cn("mt-3 flex flex-wrap gap-2", className)}>
      {citations.map((c) => (
        <span
          key={c.entity_id}
          title={c.type ? `${c.type} · id ${c.entity_id}` : `id ${c.entity_id}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-navy-100 bg-navy-50/60 px-2.5 py-1 text-xs font-medium text-navy-700"
        >
          <span className="size-1.5 rounded-full bg-steel-500" />
          <span className="max-w-[16ch] truncate">{c.label}</span>
          <ExternalLink size={10} className="text-subtle" />
        </span>
      ))}
    </div>
  );
}
