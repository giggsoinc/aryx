"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

interface Props {
  id: string;
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

const STORAGE_PREFIX = "pipeline-fold:";

/** Collapsible wrapper for one Pipeline-tab component. Open/closed state
 *  persists per section (localStorage, keyed by `id`) so folding e.g. the
 *  finished early stages stays folded across a refresh. The section's own
 *  scroll-anchor id lives on this wrapper, not the inner panel, so
 *  PipelineNav's anchor links keep working whether the section is expanded
 *  when a link is clicked, and PipelineNav also expands it if it isn't. */
export function FoldableSection({ id, title, defaultOpen = true, children }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_PREFIX + id);
    if (stored !== null) setOpen(stored === "1");
    setHydrated(true);
  }, [id]);

  // PipelineNav dispatches this before scrolling so a folded section expands
  // instead of the nav link landing on an empty collapsed header.
  useEffect(() => {
    const onExpand = (e: Event) => {
      if ((e as CustomEvent<string>).detail === id) setOpen(true);
    };
    window.addEventListener("pipeline-expand", onExpand);
    return () => window.removeEventListener("pipeline-expand", onExpand);
  }, [id]);

  useEffect(() => {
    if (hydrated) window.localStorage.setItem(STORAGE_PREFIX + id, open ? "1" : "0");
  }, [id, open, hydrated]);

  return (
    <div id={id} className="scroll-mt-20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="focus-ring group flex w-full items-center gap-2 px-6 py-1.5 text-left"
      >
        <ChevronDown
          size={14}
          className={cn(
            "shrink-0 text-navy-400 transition-transform group-hover:text-navy-600",
            open ? "rotate-0" : "-rotate-90",
          )}
        />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-navy-400 group-hover:text-navy-600">
          {title}
        </span>
      </button>
      {open && children}
    </div>
  );
}
