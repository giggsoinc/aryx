"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

export interface PipelineNavItem {
  id: string;
  label: string;
}

interface Props {
  items: PipelineNavItem[];
}

/** Sticky left-rail table of contents for the Pipeline page — one entry per
 *  component section (matched by id to the section wrappers in
 *  dashboard-observability/page.tsx). Highlights whichever section is
 *  currently in view and smooth-scrolls to a section on click, so a long
 *  stack of C01-C14 panels stays navigable without endless scrolling. */
export function PipelineNav({ items }: Props) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    const visible = new Map<string, number>();
    observerRef.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.set(entry.target.id, entry.intersectionRatio);
          else visible.delete(entry.target.id);
        }
        if (visible.size === 0) return;
        // Whichever tracked section has the most of itself on screen right
        // now — steadier than "topmost" when several short panels fit
        // in the viewport at once.
        const top = [...visible.entries()].sort((a, b) => b[1] - a[1])[0];
        if (top) setActiveId(top[0]);
      },
      { rootMargin: "-96px 0px -60% 0px", threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    for (const item of items) {
      const el = document.getElementById(item.id);
      if (el) observerRef.current.observe(el);
    }
    return () => observerRef.current?.disconnect();
  }, [items]);

  return (
    <nav className="sticky top-20 hidden h-fit w-56 shrink-0 self-start pl-4 lg:block">
      <div className="text-[10px] font-bold uppercase tracking-wider text-subtle">
        Pipeline
      </div>
      <ul className="mt-2 space-y-0.5 border-l border-navy-100">
        {items.map((item) => {
          const active = item.id === activeId;
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                onClick={(e) => {
                  // Expand the section first (it may be folded) — see
                  // FoldableSection — then scroll once its layout settles,
                  // rather than landing on a collapsed, empty header.
                  e.preventDefault();
                  window.dispatchEvent(new CustomEvent("pipeline-expand", { detail: item.id }));
                  requestAnimationFrame(() => {
                    document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                  });
                }}
                className={cn(
                  "focus-ring -ml-px block border-l-2 py-1.5 pl-3 text-[12px] transition-colors",
                  active
                    ? "border-navy-800 font-semibold text-navy-900"
                    : "border-transparent text-subtle hover:border-navy-200 hover:text-navy-700",
                )}
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
