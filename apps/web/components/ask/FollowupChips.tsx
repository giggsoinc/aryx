"use client";

import { cn } from "@/lib/cn";

interface Props {
  prompts: string[];
  onPick: (text: string) => void;
  className?: string;
}

/** Tappable follow-up prompts shown beneath the latest assistant message
 *  or as starter suggestions on an empty chat. */
export function FollowupChips({ prompts, onPick, className }: Props) {
  if (!prompts.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {prompts.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onPick(p)}
          className="focus-ring rounded-full border border-navy-100 bg-white px-4 py-2 text-sm text-navy-700 transition-colors hover:border-steel-400 hover:bg-navy-50"
        >
          {p}
        </button>
      ))}
    </div>
  );
}
